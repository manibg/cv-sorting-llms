"""Unit tests for ranking, skill filter, and export helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from matcher import CandidateMatch, ModelMatchResult
from parsers import ParsedDocument
from ranker import (
    apply_skill_filter,
    format_console_table,
    matches_to_dict,
    rank_candidates,
    save_results,
)


def _match(name: str, score: float, text: str = "", path: str | None = None) -> CandidateMatch:
    resume = ParsedDocument(
        source_path=path or f"{name}.txt",
        raw_text=text or f"{name} python",
        candidate_name=name,
        skills=["python"] if "python" in (text or name).lower() else [],
    )
    return CandidateMatch(
        resume=resume,
        model_results=[ModelMatchResult(model_name="llama3.2", overall_score=score)],
        final_score=score,
    )


class RankerTests(unittest.TestCase):
    def test_rank_candidates_orders_by_score_desc(self):
        matches = [_match("Low", 40), _match("High", 90), _match("Mid", 70)]
        ranked = rank_candidates(matches)
        self.assertEqual([m.resume.candidate_name for m in ranked], ["High", "Mid", "Low"])
        self.assertEqual([m.rank for m in ranked], [1, 2, 3])

    def test_rank_candidates_stable_tie_break_by_name(self):
        matches = [_match("Zoe", 50), _match("Amy", 50)]
        ranked = rank_candidates(matches)
        self.assertEqual([m.resume.candidate_name for m in ranked], ["Amy", "Zoe"])

    def test_skill_filter_penalizes_missing_skills(self):
        matches = [
            _match("Fit", 80, text="python django aws"),
            _match("Miss", 80, text="excel powerpoint"),
        ]
        adjusted = apply_skill_filter(matches, ["python"])
        by_name = {m.resume.candidate_name: m.final_score for m in adjusted}
        self.assertEqual(by_name["Fit"], 80)
        self.assertLess(by_name["Miss"], 80)

    def test_skill_filter_noop_when_empty(self):
        matches = [_match("A", 10)]
        self.assertEqual(apply_skill_filter(matches, [])[0].final_score, 10)

    def test_save_and_serialize(self):
        with tempfile.TemporaryDirectory() as tmp:
            ranked = rank_candidates([_match("Alice", 88, text="python")])
            payload = matches_to_dict(ranked, job_path="jd.txt", models=["llama3.2", "gemma2"])
            out = Path(tmp) / "out.json"
            saved = save_results(payload, str(out))
            loaded = json.loads(Path(saved).read_text(encoding="utf-8"))
            self.assertEqual(loaded["candidate_count"], 1)
            self.assertEqual(loaded["ranked_cvs"][0]["rank"], 1)
            self.assertEqual(loaded["models"], ["llama3.2", "gemma2"])

    def test_format_console_table_empty(self):
        self.assertIn("No candidates", format_console_table([]))


if __name__ == "__main__":
    unittest.main()
