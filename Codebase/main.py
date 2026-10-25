#!/usr/bin/env python3
"""
CV Sorting using LLMs — Capstone Project CS[02]

Entry point (required by submission rules).

Pipeline:
  1. Parse job description
  2. Discover + parse candidate CVs (txt/pdf/docx)
  3. Score each CV with two free local Ollama models (llama3.2 + gemma2)
  4. Aggregate scores and emit a ranked list (console + JSON)

Examples:
  python main.py --cvs ./sample_data/cvs --jd ./sample_data/job_description.txt
  python main.py --cvs ./cvs --jd ./jd.txt --models llama3.2,gemma2
  python main.py --cvs ./cvs --jd ./jd.txt --mock   # offline / CI without Ollama
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List

from config import AppConfig
from llm_client import create_provider
from matcher import Matcher
from parsers import DocumentParseError, discover_cv_files, parse_cv, parse_job_description
from ranker import (
    apply_skill_filter,
    format_console_table,
    matches_to_dict,
    rank_candidates,
    save_results,
)


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for main.py."""
    parser = argparse.ArgumentParser(
        description="Rank candidate CVs against a job description using local LLMs (Ollama)."
    )
    parser.add_argument(
        "--cvs",
        required=True,
        help="Path to a CV file or a directory containing CVs (.txt/.pdf/.docx).",
    )
    parser.add_argument(
        "--jd",
        required=True,
        help="Path to the job description file (.txt/.pdf/.docx).",
    )
    parser.add_argument(
        "--models",
        default=None,
        help="Comma-separated Ollama model names (default: llama3.2,gemma2).",
    )
    parser.add_argument(
        "--ollama-url",
        default=None,
        help="Ollama base URL (default: http://localhost:11434 or $OLLAMA_URL).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path for ranked JSON output (default: ./ranked_results.json).",
    )
    parser.add_argument(
        "--required-skills",
        default=None,
        help="Optional comma-separated hard skills used to refine ranking.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock LLMs (no Ollama required). Useful for tests/demo.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def configure_logging(verbose: bool) -> None:
    """Configure root logger for terminal-friendly output."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # macOS system Python often triggers a noisy urllib3 LibreSSL warning.
    try:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.NotOpenSSLWarning)
    except Exception:  # noqa: BLE001 - optional dependency path
        pass


def run_sorting(config: AppConfig) -> dict:
    """
    Execute the full CV sorting pipeline and return the results payload.

    Raises exceptions for fatal configuration / parsing problems so callers
    (including tests) can assert on failure modes.
    """
    logger = logging.getLogger("main")
    logger.info("Starting CV sorting | models=%s | mock=%s", config.models, config.use_mock_llm)

    job = parse_job_description(config.jd_path)
    if job.is_empty():
        raise ValueError(f"Job description is empty: {config.jd_path}")

    cv_files = discover_cv_files(config.cvs_path)
    logger.info("Discovered %d CV file(s)", len(cv_files))

    resumes = []
    parse_errors: List[str] = []
    for path in cv_files:
        try:
            resumes.append(parse_cv(path))
        except (DocumentParseError, OSError) as exc:
            msg = f"Skipping unreadable CV '{path}': {exc}"
            logger.warning(msg)
            parse_errors.append(msg)

    if not resumes:
        raise DocumentParseError(
            "No readable CVs available after parsing. "
            + ("; ".join(parse_errors) if parse_errors else "")
        )

    providers = [
        create_provider(
            model_name=name,
            use_mock=config.use_mock_llm,
            ollama_url=config.ollama_url,
            timeout=config.timeout_seconds,
        )
        for name in config.models
    ]

    matcher = Matcher(
        providers=providers,
        model_weights=config.model_weights,
        temperature=config.temperature,
        required_skills=config.required_skills,
    )

    matches = [matcher.match_one(resume, job) for resume in resumes]
    matches = apply_skill_filter(matches, config.required_skills)
    ranked = rank_candidates(matches)

    payload = matches_to_dict(ranked, job_path=config.jd_path, models=config.models)
    if parse_errors:
        payload["parse_warnings"] = parse_errors

    save_results(payload, config.output_path)
    print(format_console_table(ranked))
    print(f"\nSaved ranked results → {config.output_path}")
    return payload


def main(argv: List[str] | None = None) -> int:
    """CLI entrypoint. Returns a process exit code."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    config = AppConfig.from_env_and_args(
        cvs_path=args.cvs,
        jd_path=args.jd,
        models=args.models,
        ollama_url=args.ollama_url,
        output_path=args.output,
        required_skills=args.required_skills,
        use_mock_llm=args.mock,
    )

    try:
        run_sorting(config)
        return 0
    except FileNotFoundError as exc:
        logging.error("%s", exc)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (DocumentParseError, ValueError) as exc:
        logging.error("%s", exc)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 - top-level CLI guard
        logging.exception("Unexpected failure: %s", exc)
        print(f"ERROR: unexpected failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
