"""Unit tests for LLM providers and JSON parsing edge cases."""

from __future__ import annotations

import json
import unittest

from llm_client import (
    LLMError,
    MockLLMProvider,
    create_provider,
    parse_json_response,
)


class LLMClientTests(unittest.TestCase):
    def test_parse_json_response_plain(self):
        data = parse_json_response('{"overall_score": 80, "explanation": "good"}')
        self.assertEqual(data["overall_score"], 80)

    def test_parse_json_response_markdown_fence(self):
        raw = """Here is the result:
```json
{"overall_score": 55, "gaps": ["missing java"]}
```
"""
        data = parse_json_response(raw)
        self.assertEqual(data["overall_score"], 55)
        self.assertEqual(data["gaps"], ["missing java"])

    def test_parse_json_response_with_prose_wrapper(self):
        raw = 'Sure.\n{"overall_score": 10, "explanation": "weak"}\nThanks'
        data = parse_json_response(raw)
        self.assertEqual(data["overall_score"], 10)

    def test_parse_json_response_empty(self):
        with self.assertRaises(LLMError):
            parse_json_response("   ")

    def test_parse_json_response_invalid(self):
        with self.assertRaises(LLMError):
            parse_json_response("not json at all")

    def test_mock_provider_returns_valid_json(self):
        provider = MockLLMProvider("llama3.2")
        raw = provider.generate(
            "system",
            "JOB DESCRIPTION:\npython django aws\nCANDIDATE RESUME:\npython django flask",
        )
        data = json.loads(raw)
        self.assertGreaterEqual(data["overall_score"], 0)
        self.assertLessEqual(data["overall_score"], 100)
        self.assertIn("requirement_scores", data)

    def test_create_provider_mock_flag(self):
        provider = create_provider("gemma2", use_mock=True)
        self.assertIsInstance(provider, MockLLMProvider)

    def test_create_provider_mock_prefix(self):
        provider = create_provider("mock-llama")
        self.assertIsInstance(provider, MockLLMProvider)

    def test_parse_json_response_repairs_missing_comma_between_fields(self):
        # Mimics llama3.2 output that caused: Expecting ',' delimiter
        raw = """{
  "overall_score": 88,
  "requirement_scores": {"skills_match": 90},
  "strengths": ["python"],
  "gaps": ["kubernetes"]
  "explanation": "Strong backend match"
}"""
        data = parse_json_response(raw)
        self.assertEqual(data["overall_score"], 88)
        self.assertEqual(data["explanation"], "Strong backend match")

    def test_parse_json_response_repairs_trailing_comma(self):
        raw = '{"overall_score": 70, "gaps": ["x"],}'
        data = parse_json_response(raw)
        self.assertEqual(data["overall_score"], 70)


if __name__ == "__main__":
    unittest.main()
