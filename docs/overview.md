# Project overview

## Summary

**CV Sorting using LLMs** ranks candidate CVs against a single job description.

Recruiters (or evaluators) supply one JD and one or more CVs. The system parses the files, asks local LLMs to score each candidate, then returns a ranked list (console table + JSON).

No cloud LLM APIs are required for the default path. Scoring runs on your machine through **Ollama**.

## LLMs used

| Piece | Detail |
|--------|--------|
| **Runtime** | [Ollama](https://ollama.com) — local HTTP API (`http://localhost:11434`) |
| **Default models** | **llama3.2** and **gemma2** |
| **Scoring style** | Both models score each CV; scores are averaged (equal weight by default) |
| **Why two models** | Capstone requires at least two LLMs; dual scoring reduces single-model bias |
| **Offline option** | `--mock` uses deterministic mock LLMs (no Ollama) for demos and CI |

You can override models with `--models` (comma-separated Ollama names).

## Features

- **Multi-format input** — CVs and JD as `.txt`, `.pdf`, or `.docx` (mixed formats OK)
- **Dual local LLM scoring** — llama3.2 + gemma2 via Ollama (JSON-mode responses)
- **Ranked output** — console table + `ranked_results.json` (scores, strengths, gaps)
- **Optional skill filter** — `--required-skills` to refine ranking with hard skills
- **Mock mode** — run without Ollama for tests and offline demos
- **Demo UI** — browser app (`ui_server.py` on port `7860`) for uploads / paste JD
- **Plug-and-play LLM layer** — implement `LLMProvider` to swap backends without rewriting match/rank logic
- **Unit tests** — stdlib `unittest` suite under `Codebase/test_*.py`

## Non-functional requirements

| Area | Expectation |
|------|-------------|
| **Privacy** | Default path keeps CVs/JD on the local machine (Ollama local). No third-party LLM cloud call unless you add a new provider. |
| **Reliability** | Per-model errors are captured; ranking can still proceed with successful models. Mock mode supports CI without Ollama. |
| **Usability** | CLI for evaluation (`main.py`); optional UI for demos; clear console + JSON output. |
| **Maintainability** | Plain Python modules (no LangChain). Config, parsers, prompts, LLM client, matcher, and ranker are separated. |
| **Portability** | Works with free local models; dependencies listed in `requirements.txt`. |
| **Testability** | Edge-case unit tests; mock provider for deterministic runs. |
| **Performance** | Depends on local hardware and model size. Timeout default is 120s per Ollama call. Prefer fewer CVs or mock mode for quick checks. |

## Scope

**In scope:** parse → match with local LLMs → rank → export; CLI + demo UI.

**Out of scope:** production ATS integration, cloud hosting, fine-tuning models, multi-JD batch jobs in one run.
