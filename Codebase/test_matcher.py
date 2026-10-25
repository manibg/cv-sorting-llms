"""Unit tests for matching and score aggregation."""

from __future__ import annotations

import unittest

from llm_client import LLMProvider, MockLLMProvider
from matcher import Matcher, ModelMatchResult, aggregate_scores
from parsers import ParsedDocument


class BrokenProvider(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        raise RuntimeError("boom")


class InvalidJsonProvider(LLMProvider):
    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        return "I think this candidate is great but I will not return JSON."


def _doc(text: str, name: str = "Cand", path: str = "c.txt") -> ParsedDocument:
    return ParsedDocument(
        source_path=path,
        raw_text=text,
        candidate_name=name,
        skills=["python"] if "python" in text.lower() else [],
    )


class MatcherTests(unittest.TestCase):
    def test_matcher_dual_model_aggregation(self):
        providers = [MockLLMProvider("llama3.2"), MockLLMProvider("gemma2")]
        matcher = Matcher(providers=providers, model_weights={"llama3.2": 0.5, "gemma2": 0.5})
        job = _doc("Looking for python django aws engineer", name="JD", path="jd.txt")
        resume = _doc("Senior engineer with python django aws experience", name="Alice", path="a.txt")
        result = matcher.match_one(resume, job)
        self.assertEqual(len(result.model_results), 2)
        self.assertTrue(all(r.ok for r in result.model_results))
        self.assertGreater(result.final_score, 0)

    def test_empty_resume_scores_zero(self):
        providers = [MockLLMProvider("llama3.2"), MockLLMProvider("gemma2")]
        matcher = Matcher(providers=providers)
        job = _doc("python developer", path="jd.txt")
        resume = _doc("   ", name="Empty", path="e.txt")
        result = matcher.match_one(resume, job)
        self.assertEqual(result.final_score, 0.0)
        self.assertTrue(all(r.error for r in result.model_results))

    def test_empty_job_raises(self):
        providers = [MockLLMProvider("llama3.2")]
        matcher = Matcher(providers=providers)
        with self.assertRaises(ValueError):
            matcher.match_one(_doc("python"), _doc("  ", path="jd.txt"))

    def test_invalid_json_from_model_is_captured(self):
        matcher = Matcher(providers=[InvalidJsonProvider("llama3.2")])
        result = matcher.match_one(_doc("python"), _doc("python developer", path="jd.txt"))
        self.assertFalse(result.model_results[0].ok)
        self.assertEqual(result.final_score, 0.0)

    def test_aggregate_scores_equal_weights(self):
        results = [
            ModelMatchResult(model_name="llama3.2", overall_score=80),
            ModelMatchResult(model_name="gemma2", overall_score=60),
        ]
        self.assertEqual(aggregate_scores(results, {"llama3.2": 0.5, "gemma2": 0.5}), 70.0)

    def test_aggregate_scores_ignores_failed_models(self):
        results = [
            ModelMatchResult(model_name="llama3.2", overall_score=90),
            ModelMatchResult(model_name="gemma2", overall_score=0, error="down"),
        ]
        self.assertEqual(aggregate_scores(results, {"llama3.2": 0.5, "gemma2": 0.5}), 90.0)

    def test_aggregate_scores_all_failed(self):
        results = [
            ModelMatchResult(model_name="llama3.2", overall_score=0, error="x"),
            ModelMatchResult(model_name="gemma2", overall_score=0, error="y"),
        ]
        self.assertEqual(aggregate_scores(results), 0.0)

    def test_matcher_requires_provider(self):
        with self.assertRaises(ValueError):
            Matcher(providers=[])

    def test_provider_runtime_error_is_isolated(self):
        matcher = Matcher(providers=[BrokenProvider("llama3.2"), MockLLMProvider("gemma2")])
        result = matcher.match_one(
            _doc("python django"),
            _doc("python django developer", path="jd.txt"),
        )
        self.assertIsNotNone(result.model_results[0].error)
        self.assertTrue(result.model_results[1].ok)
        self.assertGreater(result.final_score, 0)


if __name__ == "__main__":
    unittest.main()
