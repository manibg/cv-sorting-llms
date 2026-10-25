"""End-to-end CLI / pipeline tests using mock LLMs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from config import AppConfig
from main import main, run_sorting
from parsers import DocumentParseError


def _write_sample_corpus(root: Path) -> tuple[Path, Path]:
    cvs = root / "cvs"
    cvs.mkdir()
    (cvs / "alice.txt").write_text(
        "Alice Johnson\nalice@example.com\n"
        "6 years of experience with Python, Django, AWS, Docker.\n"
        "Built REST APIs and microservices.\n"
        "B.Tech Computer Science\n",
        encoding="utf-8",
    )
    (cvs / "bob.txt").write_text(
        "Bob Smith\nbob@example.com\n"
        "3 years of experience with Java, Spring, SQL.\n"
        "MBA Finance\n",
        encoding="utf-8",
    )
    (cvs / "cara.txt").write_text(
        "Cara Lee\ncara@example.com\n"
        "8 years of experience with Python, FastAPI, Kubernetes, AWS, NLP.\n"
        "M.S. Machine Learning\n",
        encoding="utf-8",
    )
    jd = root / "job_description.txt"
    jd.write_text(
        "Senior Python Backend Engineer\n"
        "Must have: Python, Django or FastAPI, AWS, Docker.\n"
        "Nice to have: Kubernetes, NLP.\n"
        "Responsibilities: design APIs, own microservices, mentor juniors.\n",
        encoding="utf-8",
    )
    return cvs, jd


class MainPipelineTests(unittest.TestCase):
    def test_run_sorting_mock_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cvs, jd = _write_sample_corpus(root)
            out = root / "ranked.json"
            config = AppConfig.from_env_and_args(
                cvs_path=str(cvs),
                jd_path=str(jd),
                models="llama3.2,gemma2",
                output_path=str(out),
                use_mock_llm=True,
            )
            payload = run_sorting(config)
            self.assertEqual(payload["candidate_count"], 3)
            self.assertTrue(out.exists())
            ranks = [row["rank"] for row in payload["ranked_cvs"]]
            self.assertEqual(ranks, [1, 2, 3])
            names = [row["candidate_name"] for row in payload["ranked_cvs"]]
            self.assertEqual(names[-1], "Bob Smith")

    def test_main_cli_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cvs, jd = _write_sample_corpus(root)
            out = root / "out.json"
            code = main(
                [
                    "--cvs",
                    str(cvs),
                    "--jd",
                    str(jd),
                    "--output",
                    str(out),
                    "--mock",
                    "--models",
                    "llama3.2,gemma2",
                ]
            )
            self.assertEqual(code, 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["candidate_count"], 3)

    def test_main_cli_missing_jd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cvs = root / "cvs"
            cvs.mkdir()
            (cvs / "a.txt").write_text("A\npython", encoding="utf-8")
            code = main(["--cvs", str(cvs), "--jd", str(root / "missing.txt"), "--mock"])
            self.assertEqual(code, 2)

    def test_run_sorting_no_readable_cvs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cvs = root / "cvs"
            cvs.mkdir()
            (cvs / "bad.pdf").write_bytes(b"not-a-pdf")
            jd = root / "jd.txt"
            jd.write_text("python engineer", encoding="utf-8")
            config = AppConfig.from_env_and_args(
                cvs_path=str(cvs),
                jd_path=str(jd),
                use_mock_llm=True,
                output_path=str(root / "o.json"),
            )
            with self.assertRaises(DocumentParseError):
                run_sorting(config)

    def test_required_skills_refinement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cvs, jd = _write_sample_corpus(root)
            out = root / "ranked.json"
            config = AppConfig.from_env_and_args(
                cvs_path=str(cvs),
                jd_path=str(jd),
                output_path=str(out),
                required_skills="kubernetes",
                use_mock_llm=True,
            )
            payload = run_sorting(config)
            top = payload["ranked_cvs"][0]["candidate_name"]
            self.assertEqual(top, "Cara Lee")


if __name__ == "__main__":
    unittest.main()
