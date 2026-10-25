"""
Pluggable LLM clients.

Providers implement a tiny interface so new backends can be swapped without
touching matching/ranking logic. Default backend is Ollama (local, free).
"""

from __future__ import annotations

import abc
import json
import logging
import re
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when an LLM call fails or returns unusable content."""


class LLMProvider(abc.ABC):
    """Abstract LLM provider — plug-and-play interface."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    @abc.abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        """Return raw text completion from the model."""


class OllamaProvider(LLMProvider):
    """
    Free local LLM access via the Ollama HTTP API.

    Expects models such as llama3.2 and gemma2 to be pulled already:
        ollama pull llama3.2
        ollama pull gemma2
    """

    def __init__(self, model_name: str, base_url: str = "http://localhost:11434", timeout: int = 120):
        super().__init__(model_name)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        """Call Ollama /api/chat and return the assistant message content."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model_name,
            "stream": False,
            # Force JSON-mode when supported — reduces broken llama3.2 payloads.
            "format": "json",
            "options": {"temperature": temperature},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            logger.error("Ollama request failed for model=%s: %s", self.model_name, exc)
            raise LLMError(
                f"Cannot reach Ollama at {self.base_url} for model '{self.model_name}'. "
                f"Is Ollama running? Details: {exc}"
            ) from exc

        if response.status_code != 200:
            logger.error(
                "Ollama HTTP %s for model=%s: %s",
                response.status_code,
                self.model_name,
                response.text[:500],
            )
            raise LLMError(
                f"Ollama returned HTTP {response.status_code} for '{self.model_name}': "
                f"{response.text[:300]}"
            )

        try:
            data = response.json()
            content = data["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMError(f"Unexpected Ollama response for '{self.model_name}': {exc}") from exc

        if not content or not str(content).strip():
            raise LLMError(f"Empty response from model '{self.model_name}'")
        return str(content)


class MockLLMProvider(LLMProvider):
    """
    Deterministic offline provider for unit tests and demos without Ollama.

    Scores are derived from simple keyword overlap so edge-case tests stay stable.
    """

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        """Produce a JSON score payload from keyword overlap heuristics."""
        # Split prompt into JD / resume sections when present.
        jd_part, resume_part = _split_prompt_sections(user_prompt)
        jd_tokens = set(_tokenize(jd_part))
        resume_tokens = set(_tokenize(resume_part))
        if not jd_tokens:
            overlap = 0.0
        else:
            overlap = len(jd_tokens & resume_tokens) / max(len(jd_tokens), 1)

        overall = round(min(100.0, max(0.0, overlap * 100.0)), 2)
        # Slight model-specific bias so dual-model aggregation is exercisable in tests.
        if "gemma" in self.model_name.lower():
            overall = round(min(100.0, overall * 0.95 + 2.0), 2)
        elif "llama" in self.model_name.lower():
            overall = round(min(100.0, overall * 1.02), 2)

        payload = {
            "overall_score": overall,
            "requirement_scores": {
                "skills_match": overall,
                "experience_match": max(0.0, overall - 5),
                "education_match": max(0.0, overall - 10),
                "responsibilities_match": max(0.0, overall - 3),
            },
            "strengths": ["Keyword overlap with job description"] if overall >= 40 else [],
            "gaps": ["Limited keyword overlap with job description"] if overall < 60 else [],
            "explanation": (
                f"Mock({self.model_name}) overlap={overlap:.2f}; "
                f"shared_tokens={len(jd_tokens & resume_tokens)}."
            ),
        }
        return json.dumps(payload)


def create_provider(
    model_name: str,
    *,
    use_mock: bool = False,
    ollama_url: str = "http://localhost:11434",
    timeout: int = 120,
) -> LLMProvider:
    """
    Factory for LLM providers.

    Swap backends here without changing matcher/ranker code.
    """
    if use_mock or model_name.lower().startswith("mock"):
        logger.info("Using MockLLMProvider for model=%s", model_name)
        return MockLLMProvider(model_name)
    logger.info("Using OllamaProvider model=%s url=%s", model_name, ollama_url)
    return OllamaProvider(model_name=model_name, base_url=ollama_url, timeout=timeout)


def parse_json_response(raw: str) -> Dict[str, Any]:
    """
    Extract a JSON object from an LLM response.

    Handles common edge cases: markdown fences, leading prose, trailing commas,
    and other small syntax mistakes smaller local models often produce.
    """
    if raw is None:
        raise LLMError("LLM returned null response")

    text = raw.strip()
    if not text:
        raise LLMError("LLM returned empty response")

    # Strip ```json ... ``` fences if present.
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    last_error: Optional[Exception] = None
    for candidate in candidates:
        for variant in _json_repair_variants(candidate):
            try:
                data = json.loads(variant)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError as exc:
                last_error = exc
                continue

    detail = f": {last_error}" if last_error else ""
    raise LLMError(f"Could not parse JSON from LLM response{detail}. Snippet: {raw[:200]!r}")


def _json_repair_variants(text: str) -> List[str]:
    """
    Yield progressively repaired versions of nearly-valid JSON.

    Local models (especially llama3.2) sometimes omit commas between fields
    or leave trailing commas after the last list/object item.
    """
    seen = set()
    variants = [text, _repair_common_json_issues(text)]
    for variant in variants:
        if variant and variant not in seen:
            seen.add(variant)
            yield variant


def _repair_common_json_issues(text: str) -> str:
    """Apply lightweight fixes for frequent LLM JSON mistakes."""
    fixed = text.strip()
    # Remove trailing commas before } or ]
    fixed = re.sub(r",(\s*[}\]])", r"\1", fixed)
    # Insert missing commas between }|"|number|true|false|null and next "key"
    # Example broken shape:
    #   "gaps": ["a"]
    #   "explanation": "..."
    fixed = re.sub(r'([}\]"0-9]|true|false|null)\s*\n\s*(")', r"\1,\n\2", fixed)
    # Insert missing commas between array/object values on consecutive lines:
    #   "a"
    #   "b"
    fixed = re.sub(r'(")\s*\n\s*(")', r"\1,\n\2", fixed)
    # Normalize smart quotes that break json.loads
    fixed = fixed.replace("“", '"').replace("”", '"').replace("’", "'")
    return fixed


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9_+#./-]{2,}", (text or "").lower())


def _split_prompt_sections(prompt: str) -> tuple[str, str]:
    """Best-effort split of match prompt into JD and resume parts."""
    marker_jd = "JOB DESCRIPTION:"
    marker_cv = "CANDIDATE RESUME:"
    if marker_jd in prompt and marker_cv in prompt:
        jd = prompt.split(marker_jd, 1)[1].split(marker_cv, 1)[0]
        resume = prompt.split(marker_cv, 1)[1]
        return jd, resume
    return prompt, prompt
