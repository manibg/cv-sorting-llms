"""
Ranking and result export for sorted CVs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from matcher import CandidateMatch

logger = logging.getLogger(__name__)


def rank_candidates(matches: List[CandidateMatch]) -> List[CandidateMatch]:
    """
    Sort candidates by final_score descending.

    Tie-breaker: candidate name, then source path (stable, deterministic).
    """
    ordered = sorted(
        matches,
        key=lambda m: (
            -(m.final_score or 0.0),
            (m.resume.candidate_name or "").lower(),
            m.resume.source_path.lower(),
        ),
    )
    for index, match in enumerate(ordered, start=1):
        match.rank = index
    return ordered


def matches_to_dict(matches: List[CandidateMatch], job_path: str, models: List[str]) -> Dict[str, Any]:
    """Serialize ranked matches into a JSON-friendly dictionary."""
    ranked = []
    for match in matches:
        per_model = []
        for result in match.model_results:
            per_model.append(
                {
                    "model": result.model_name,
                    "overall_score": result.overall_score,
                    "requirement_scores": result.requirement_scores,
                    "strengths": result.strengths,
                    "gaps": result.gaps,
                    "explanation": result.explanation,
                    "error": result.error,
                }
            )
        ranked.append(
            {
                "rank": match.rank,
                "final_score": match.final_score,
                "candidate_name": match.resume.candidate_name,
                "source_path": match.resume.source_path,
                "email": match.resume.email,
                "skills": match.resume.skills,
                "experience_years": match.resume.experience_years,
                "model_scores": per_model,
            }
        )

    return {
        "job_description": job_path,
        "models": models,
        "candidate_count": len(ranked),
        "ranked_cvs": ranked,
    }


def save_results(payload: Dict[str, Any], output_path: str) -> str:
    """Write ranked results JSON to disk and return the absolute path."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Wrote ranked results to %s", path.resolve())
    return str(path.resolve())


def format_console_table(matches: List[CandidateMatch]) -> str:
    """Human-readable ranked table for terminal output."""
    if not matches:
        return "No candidates ranked."

    lines = [
        "",
        "=" * 72,
        f"{'Rank':<6}{'Score':<10}{'Candidate':<28}{'Source'}",
        "-" * 72,
    ]
    for match in matches:
        name = match.resume.candidate_name or Path(match.resume.source_path).stem
        source = Path(match.resume.source_path).name
        lines.append(f"{match.rank:<6}{match.final_score:<10.2f}{name[:26]:<28}{source}")
    lines.append("=" * 72)

    # Append short explanations for transparency.
    lines.append("")
    lines.append("Per-candidate explanations:")
    for match in matches:
        name = match.resume.candidate_name or Path(match.resume.source_path).stem
        lines.append(f"\n[{match.rank}] {name} — final_score={match.final_score}")
        for result in match.model_results:
            if result.error:
                lines.append(f"  - {result.model_name}: ERROR — {result.error}")
            else:
                expl = (result.explanation or "").replace("\n", " ")
                lines.append(f"  - {result.model_name}: {result.overall_score:.2f} | {expl[:220]}")
    return "\n".join(lines)


def apply_skill_filter(
    matches: List[CandidateMatch],
    required_skills: Optional[List[str]],
) -> List[CandidateMatch]:
    """
    Soft filter used for interactive refinement.

    Candidates missing all required skills are kept but receive a score penalty
    so ranking remains explainable rather than silently dropping people.
    """
    if not required_skills:
        return matches

    required = [s.lower().strip() for s in required_skills if s.strip()]
    if not required:
        return matches

    adjusted: List[CandidateMatch] = []
    for match in matches:
        text = (match.resume.raw_text or "").lower()
        skills = {s.lower() for s in match.resume.skills}
        hits = sum(1 for skill in required if skill in skills or skill in text)
        if hits == 0:
            match.final_score = round(match.final_score * 0.35, 2)
            logger.info(
                "Applied skill-filter penalty to %s (required=%s)",
                match.resume.source_path,
                required_skills,
            )
        adjusted.append(match)
    return adjusted
