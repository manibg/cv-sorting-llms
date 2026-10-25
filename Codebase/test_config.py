"""Unit tests for configuration helpers."""

from __future__ import annotations

import os
import unittest

from config import DEFAULT_MODELS, AppConfig


class ConfigTests(unittest.TestCase):
    def test_default_models_are_llama_and_gemma(self):
        self.assertEqual(DEFAULT_MODELS, ["llama3.2", "gemma2"])

    def test_from_env_and_args_parses_models_and_skills(self):
        os.environ.pop("CV_SORT_MODELS", None)
        os.environ.pop("OLLAMA_URL", None)
        cfg = AppConfig.from_env_and_args(
            cvs_path="./cvs",
            jd_path="./jd.txt",
            models="llama3.2,gemma2",
            required_skills="python, aws",
            ollama_url="http://127.0.0.1:11434/",
        )
        self.assertEqual(cfg.models, ["llama3.2", "gemma2"])
        self.assertEqual(cfg.required_skills, ["python", "aws"])
        self.assertEqual(cfg.ollama_url, "http://127.0.0.1:11434")
        self.assertAlmostEqual(sum(cfg.model_weights.values()), 1.0, places=9)

    def test_env_overrides(self):
        os.environ["CV_SORT_MODELS"] = "llama3.2,gemma2"
        os.environ["OLLAMA_URL"] = "http://ollama.local:11434"
        os.environ["CV_SORT_OUTPUT"] = "./custom.json"
        try:
            cfg = AppConfig.from_env_and_args(cvs_path="c", jd_path="j")
            self.assertEqual(cfg.models, ["llama3.2", "gemma2"])
            self.assertEqual(cfg.ollama_url, "http://ollama.local:11434")
            self.assertEqual(cfg.output_path, "./custom.json")
        finally:
            os.environ.pop("CV_SORT_MODELS", None)
            os.environ.pop("OLLAMA_URL", None)
            os.environ.pop("CV_SORT_OUTPUT", None)


if __name__ == "__main__":
    unittest.main()
