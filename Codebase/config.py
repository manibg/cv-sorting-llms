"""
Central configuration for the CV Sorting pipeline.

Defaults favour local Ollama models (llama3.2 + gemma2). Every value can be
overridden from the CLI or environment variables so the system stays plug-and-play.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


# Default dual-LLM pair required by the capstone (at least two LLMs).
DEFAULT_MODELS: List[str] = ["llama3.2", "gemma2"]

# Equal weight so both models contribute equally to the final rank.
DEFAULT_MODEL_WEIGHTS = {
    "llama3.2": 0.5,
    "gemma2": 0.5,
}


@dataclass
class AppConfig:
    """Runtime configuration for a single sorting run."""

    cvs_path: str
    jd_path: str
    models: List[str] = field(default_factory=lambda: list(DEFAULT_MODELS))
    model_weights: dict = field(default_factory=lambda: dict(DEFAULT_MODEL_WEIGHTS))
    ollama_url: str = "http://localhost:11434"
    output_path: str = "./ranked_results.json"
    required_skills: List[str] = field(default_factory=list)
    temperature: float = 0.1
    timeout_seconds: int = 120
    use_mock_llm: bool = False

    @classmethod
    def from_env_and_args(
        cls,
        cvs_path: str,
        jd_path: str,
        models: str | None = None,
        ollama_url: str | None = None,
        output_path: str | None = None,
        required_skills: str | None = None,
        use_mock_llm: bool = False,
    ) -> "AppConfig":
        """
        Build config from CLI values with environment-variable fallbacks.

        Environment variables:
            OLLAMA_HOST / OLLAMA_URL  - Ollama base URL
            CV_SORT_MODELS          - comma-separated model names
            CV_SORT_OUTPUT           - ranked results output path
        """
        env_url = os.environ.get("OLLAMA_URL") or os.environ.get("OLLAMA_HOST")
        resolved_url = ollama_url or env_url or "http://localhost:11434"

        env_models = os.environ.get("CV_SORT_MODELS")
        model_list = _parse_csv(models or env_models) or list(DEFAULT_MODELS)

        weights = {}
        equal = 1.0 / len(model_list)
        for name in model_list:
            weights[name] = DEFAULT_MODEL_WEIGHTS.get(name, equal)

        skills = _parse_csv(required_skills)

        return cls(
            cvs_path=cvs_path,
            jd_path=jd_path,
            models=model_list,
            model_weights=weights,
            ollama_url=resolved_url.rstrip("/"),
            output_path=output_path or os.environ.get("CV_SORT_OUTPUT", "./ranked_results.json"),
            required_skills=skills,
            use_mock_llm=use_mock_llm,
        )


def _parse_csv(value: str | None) -> List[str]:
    """Split a comma-separated string into trimmed non-empty tokens."""
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]
