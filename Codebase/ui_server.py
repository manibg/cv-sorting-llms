#!/usr/bin/env python3
"""
Demo UI server for CV Sorting using LLMs.

Terminal evaluation still uses main.py. This server is for interactive demos.

  python ui_server.py
  # open http://127.0.0.1:7860
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import DEFAULT_MODELS, AppConfig
from main import run_sorting
from parsers import SUPPORTED_EXTENSIONS

logger = logging.getLogger("ui_server")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
SAMPLE_CVS = BASE_DIR / "sample_data" / "cvs"
SAMPLE_JD = BASE_DIR / "sample_data" / "job_description.txt"

app = FastAPI(title="CV Sort Demo", version="1.0.0")


@app.get("/")
def index() -> FileResponse:
    """Serve the demo UI shell."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    """Report UI + Ollama availability for the status pill."""
    ollama_ok = False
    models: List[str] = []
    detail = "Ollama unreachable"
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=2)
        if resp.status_code == 200:
            ollama_ok = True
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            detail = f"{len(models)} model(s) available"
    except requests.RequestException as exc:
        detail = str(exc)
    return {
        "ok": True,
        "ollama": ollama_ok,
        "ollama_detail": detail,
        "models": models,
        "supported_cv_types": sorted(SUPPORTED_EXTENSIONS),
        "supported_jd_types": sorted(SUPPORTED_EXTENSIONS),
        "default_models": DEFAULT_MODELS,
    }


@app.get("/api/capabilities")
def capabilities() -> dict:
    """Document accepted inputs for the UI help panel."""
    return {
        "cv_inputs": {
            "formats": [".txt", ".pdf", ".docx"],
            "modes": ["one or more files", "mixed formats allowed"],
            "notes": "Upload candidate resumes. Empty or corrupt files are skipped with warnings.",
        },
        "jd_inputs": {
            "formats": [".txt", ".pdf", ".docx"],
            "modes": ["upload a file", "paste plain text"],
            "notes": "Provide exactly one job description via file or paste.",
        },
        "optional": [
            "required skills filter (comma-separated)",
            "model selection (default llama3.2 + gemma2)",
            "mock mode for offline demos without Ollama",
        ],
    }


@app.post("/api/rank")
async def rank(
    cvs: List[UploadFile] = File(default=[]),
    jd_file: Optional[UploadFile] = File(default=None),
    jd_text: str = Form(default=""),
    models: str = Form(default="llama3.2,gemma2"),
    required_skills: str = Form(default=""),
    use_mock: str = Form(default="false"),
    use_sample: str = Form(default="false"),
) -> dict:
    """
    Rank uploaded (or sample) CVs against a job description.

    Accepts multipart form data from the demo UI.
    """
    mock = _as_bool(use_mock)
    sample = _as_bool(use_sample)

    with tempfile.TemporaryDirectory(prefix="cvsort_ui_") as tmp:
        tmp_path = Path(tmp)
        cvs_dir = tmp_path / "cvs"
        cvs_dir.mkdir()
        output_path = tmp_path / "ranked_results.json"

        try:
            if sample:
                if not SAMPLE_CVS.exists() or not SAMPLE_JD.exists():
                    raise HTTPException(status_code=404, detail="Sample data not found on server.")
                for src in SAMPLE_CVS.iterdir():
                    if src.is_file() and src.suffix.lower() in SUPPORTED_EXTENSIONS:
                        shutil.copy2(src, cvs_dir / src.name)
                jd_path = tmp_path / "job_description.txt"
                shutil.copy2(SAMPLE_JD, jd_path)
            else:
                if not cvs:
                    raise HTTPException(status_code=400, detail="Upload at least one CV (.txt/.pdf/.docx).")
                await _save_uploads(cvs, cvs_dir, kind="CV")
                jd_path = await _resolve_jd(tmp_path, jd_file, jd_text)

            config = AppConfig.from_env_and_args(
                cvs_path=str(cvs_dir),
                jd_path=str(jd_path),
                models=models,
                output_path=str(output_path),
                required_skills=required_skills or None,
                use_mock_llm=mock,
            )
            payload = run_sorting(config)
            payload["run_id"] = str(uuid.uuid4())
            payload["used_mock"] = mock
            payload["used_sample"] = sample
            return payload
        except HTTPException:
            raise
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ranking failed: %s", exc)
            raise HTTPException(status_code=500, detail=f"Ranking failed: {exc}") from exc


async def _save_uploads(files: List[UploadFile], dest_dir: Path, kind: str) -> None:
    """Persist uploaded files after validating extensions."""
    saved = 0
    for upload in files:
        name = Path(upload.filename or f"upload_{saved}").name
        suffix = Path(name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported {kind} format '{suffix or '(none)'}'. Use .txt, .pdf, or .docx.",
            )
        target = dest_dir / name
        # Avoid collisions when two files share a name.
        if target.exists():
            target = dest_dir / f"{target.stem}_{saved}{target.suffix}"
        content = await upload.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"Empty {kind} file: {name}")
        target.write_bytes(content)
        saved += 1
    if saved == 0:
        raise HTTPException(status_code=400, detail=f"No valid {kind} files uploaded.")


async def _resolve_jd(tmp_path: Path, jd_file: Optional[UploadFile], jd_text: str) -> Path:
    """Resolve JD from uploaded file or pasted text."""
    text = (jd_text or "").strip()
    if jd_file is not None and jd_file.filename:
        suffix = Path(jd_file.filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported JD format '{suffix}'. Use .txt, .pdf, or .docx.",
            )
        path = tmp_path / f"job_description{suffix}"
        content = await jd_file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Job description file is empty.")
        path.write_bytes(content)
        return path

    if text:
        path = tmp_path / "job_description.txt"
        path.write_text(text, encoding="utf-8")
        return path

    raise HTTPException(
        status_code=400,
        detail="Provide a job description: upload a .txt/.pdf/.docx file or paste text.",
    )


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


# Static assets last so API routes take precedence.
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def main() -> None:
    """Run the demo UI with uvicorn."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    print("CV Sort demo UI → http://127.0.0.1:7860")
    uvicorn.run("ui_server:app", host="127.0.0.1", port=7860, reload=False)


if __name__ == "__main__":
    main()
