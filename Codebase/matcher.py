"""
Candidate–job matching using one or more LLM providers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from llm_client import LLMProvider, parse_json_response
from parsers import ParsedDocument
from prompts import MATCH_SYSTEM_PROMPT, build_match_prompt

logger = logging.getLogger(__name__)


@dataclass
class ModelMatchResult:
    """Score produced by a single LLM for one candidate."""

    model_name: str
    overall_score: float
    requirement_scores: Dict[str, float] = field(default_factory=dict)
    strengths: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    explanation: str = ""
    raw_response: str = ""
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class CandidateMatch:
    """All per-model scores for one candidate resume."""

    resume: ParsedDocument
    model_results: List[ModelMatchResult] = field(default_factory=list)
    final_score: float = 0.0
    rank: int = 0

    def successful_results(self) -> List[ModelMatchResult]:
        return [r for r in self.model_results if r.ok]


class Matcher:
    """
    Runs LLM-based matching for a resume against a job description.

    Designed to accept any LLMProvider implementation (Ollama, Mock, future APIs).
    """

    def __init__(
        self,
        providers: List[LLMProvider],
        model_weights: Optional[Dict[str, float]] = None,
        temperature: float = 0.1,
        required_skills: Optional[List[str]] = None,
    ):
        if not providers:
            raise ValueError("At least one LLM provider is required")
        self.providers = providers
        self.model_weights = model_weights or {}
        self.temperature = temperature
        self.required_skills = required_skills or []

    def match_one(self, resume: ParsedDocument, job: ParsedDocument) -> CandidateMatch:
        """Score one resume with every configured LLM and aggregate."""
        if resume.is_empty():
            logger.warning("Empty resume skipped: %s", resume.source_path)
            return CandidateMatch(
                resume=resume,
                model_results=[
                    ModelMatchResult(
                        model_name=p.model_name,
                        overall_score=0.0,
                        error="Empty resume text",
                    )
                    for p in self.providers
                ],
                final_score=0.0,
            )

        if job.is_empty():
            raise ValueError("Job description is empty; cannot match candidates")

        # Optional hard skill filter: mark zero if required skills are completely absent.
        if self.required_skills and not _has_any_required_skill(resume, self.required_skills):
            logger.info(
                "Candidate %s missing required skills filter %s",
                resume.source_path,
                self.required_skills,
            )

        results: List[ModelMatchResult] = []
        for provider in self.providers:
            results.append(self._score_with_provider(provider, resume, job))

        final = aggregate_scores(results, self.model_weights)
        return CandidateMatch(resume=resume, model_results=results, final_score=final)

    def _score_with_provider(
        self,
        provider: LLMProvider,
        resume: ParsedDocument,
        job: ParsedDocument,
    ) -> ModelMatchResult:
        """Call one provider and normalize its JSON into ModelMatchResult."""
        prompt = build_match_prompt(resume, job, self.required_skills)
        try:
            raw = provider.generate(MATCH_SYSTEM_PROMPT, prompt, temperature=self.temperature)
            data = parse_json_response(raw)
            score = _clamp_score(data.get("overall_score", 0))
            req_scores = _normalize_requirement_scores(data.get("requirement_scores"))
            return ModelMatchResult(
                model_name=provider.model_name,
                overall_score=score,
                requirement_scores=req_scores,
                strengths=_as_str_list(data.get("strengths")),
                gaps=_as_str_list(data.get("gaps")),
                explanation=str(data.get("explanation") or "").strip(),
                raw_response=raw,
            )
        except Exception as exc:  # noqa: BLE001 - isolate per-model failures
            logger.error(
                "Matching failed model=%s resume=%s: %s",
                provider.model_name,
                resume.source_path,
                exc,
            )
            return ModelMatchResult(
                model_name=provider.model_name,
                overall_score=0.0,
                error=str(exc),
            )


def aggregate_scores(
    results: List[ModelMatchResult],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """
    Weighted average of successful model scores.

    If every model failed, return 0.0.
    Missing weight entries default to equal share among successful models.
    """
    successful = [r for r in results if r.ok]
    if not successful:
        return 0.0

    weights = weights or {}
    total_weight = 0.0
    weighted_sum = 0.0
    default_w = 1.0 / len(successful)

    for result in successful:
        w = float(weights.get(result.model_name, default_w))
        if w < 0:
            continue
        weighted_sum += result.overall_score * w
        total_weight += w

    if total_weight <= 0:
        return round(sum(r.overall_score for r in successful) / len(successful), 2)
    return round(weighted_sum / total_weight, 2)


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid overall_score: {value!r}") from exc
    return round(min(100.0, max(0.0, score)), 2)


def _normalize_requirement_scores(raw: Any) -> Dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = _clamp_score(value)
        except ValueError:
            continue
    return out


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _has_any_required_skill(resume: ParsedDocument, required: List[str]) -> bool:
    haystack = (resume.raw_text or "").lower()
    skill_set = {s.lower() for s in resume.skills}
    for skill in required:
        s = skill.lower().strip()
        if not s:
            continue
        if s in skill_set or s in haystack:
            return True
    return False
