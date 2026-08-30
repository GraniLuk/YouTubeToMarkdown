"""Tests for Gemini secondary model fallback and cascade behavior in AI.py."""

import unittest
from unittest.mock import patch, MagicMock
import os

from yt2md.AI import analyze_transcript_by_length


class TestGeminiFallbackCascade(unittest.TestCase):
    """Test cases for Gemini primary -> secondary -> fallback cascade."""

    @patch("yt2md.AI.analyze_transcript_with_openrouter")
    @patch("yt2md.AI.analyze_transcript_with_gemini")
    def test_long_transcript_gemini_primary_fails_secondary_succeeds(
        self, mock_gemini, mock_openrouter
    ):
        """Long transcript (>2500 words): Gemini 3.7 fails, Gemini 3.6 succeeds."""
        env = {
            "GEMINI_API_KEY": "test-gemini-key",
            "GEMINI_PRIMARY_MODEL": "gemini-3.7-flash",
            "GEMINI_FALLBACK_MODEL": "gemini-3.6-flash",
            "OPENROUTER_API_KEY": "test-or-key",
            "OPENROUTER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "LLM_SHORT_MAX_WORDS": "1600",
            "LLM_MEDIUM_MAX_WORDS": "2500",
        }

        # First call (gemini-3.7-flash) fails, second call (gemini-3.6-flash) succeeds
        mock_gemini.side_effect = [
            Exception("503 UNAVAILABLE"),
            ("Refined text from Gemini 3.6", "Description 3.6"),
        ]

        # 2600 words transcript (long)
        long_transcript = "word " * 2600

        with patch.dict(os.environ, env, clear=True):
            results = analyze_transcript_by_length(
                transcript=long_transcript,
                ollama_model="gemma4:26b",
                ollama_base_url="http://localhost:11434",
                output_language="Polish",
                category="Fitness",
            )

        self.assertIn("cloud", results)
        self.assertEqual(results["cloud"]["model_name"], "gemini-3.6-flash")
        self.assertEqual(results["cloud"]["provider"], "gemini")
        self.assertEqual(results["cloud"]["text"], "Refined text from Gemini 3.6")

        # Gemini should be called twice (3.7 then 3.6)
        self.assertEqual(mock_gemini.call_count, 2)
        call_models = [call.kwargs.get("gemini_model_name") for call in mock_gemini.call_args_list]
        self.assertEqual(call_models, ["gemini-3.7-flash", "gemini-3.6-flash"])

        # OpenRouter should NOT be called since Gemini secondary succeeded
        mock_openrouter.assert_not_called()

    @patch("yt2md.AI.analyze_transcript_with_openrouter")
    @patch("yt2md.AI.analyze_transcript_with_gemini")
    def test_long_transcript_both_gemini_fail_openrouter_succeeds(
        self, mock_gemini, mock_openrouter
    ):
        """Long transcript: Gemini 3.7 fails, Gemini 3.6 fails, OpenRouter succeeds."""
        env = {
            "GEMINI_API_KEY": "test-gemini-key",
            "GEMINI_PRIMARY_MODEL": "gemini-3.7-flash",
            "GEMINI_FALLBACK_MODEL": "gemini-3.6-flash",
            "OPENROUTER_API_KEY": "test-or-key",
            "OPENROUTER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b:free",
            "LLM_SHORT_MAX_WORDS": "1600",
            "LLM_MEDIUM_MAX_WORDS": "2500",
        }

        # Both Gemini calls fail
        mock_gemini.side_effect = [
            Exception("503 UNAVAILABLE primary"),
            Exception("503 UNAVAILABLE secondary"),
        ]
        mock_openrouter.return_value = (
            "Refined text from OpenRouter",
            "Description OR",
        )

        long_transcript = "word " * 2600

        with patch.dict(os.environ, env, clear=True):
            results = analyze_transcript_by_length(
                transcript=long_transcript,
                ollama_model="gemma4:26b",
                ollama_base_url="http://localhost:11434",
                output_language="Polish",
                category="Fitness",
            )

        self.assertIn("cloud", results)
        self.assertEqual(results["cloud"]["model_name"], "nvidia/nemotron-3-ultra-550b-a55b:free")
        self.assertEqual(results["cloud"]["provider"], "openrouter")
        self.assertEqual(results["cloud"]["text"], "Refined text from OpenRouter")

        # Both Gemini models were tried
        self.assertEqual(mock_gemini.call_count, 2)
        # OpenRouter fallback was called
        mock_openrouter.assert_called_once()

    @patch("yt2md.AI.analyze_transcript_with_openrouter")
    @patch("yt2md.AI.analyze_transcript_with_gemini")
    def test_long_transcript_primary_gemini_succeeds(
        self, mock_gemini, mock_openrouter
    ):
        """Long transcript: Gemini 3.7 succeeds on first try."""
        env = {
            "GEMINI_API_KEY": "test-gemini-key",
            "GEMINI_PRIMARY_MODEL": "gemini-3.7-flash",
            "GEMINI_FALLBACK_MODEL": "gemini-3.6-flash",
            "OPENROUTER_API_KEY": "test-or-key",
            "LLM_SHORT_MAX_WORDS": "1600",
            "LLM_MEDIUM_MAX_WORDS": "2500",
        }

        mock_gemini.return_value = ("Refined text 3.7", "Description 3.7")
        long_transcript = "word " * 2600

        with patch.dict(os.environ, env, clear=True):
            results = analyze_transcript_by_length(
                transcript=long_transcript,
                ollama_model="gemma4:26b",
                ollama_base_url="http://localhost:11434",
                output_language="Polish",
                category="Fitness",
            )

        self.assertIn("cloud", results)
        self.assertEqual(results["cloud"]["model_name"], "gemini-3.7-flash")
        self.assertEqual(mock_gemini.call_count, 1)
        mock_openrouter.assert_not_called()

    @patch("yt2md.AI.analyze_transcript_with_openrouter")
    @patch("yt2md.AI.analyze_transcript_with_gemini")
    @patch("yt2md.AI.analyze_transcript_with_ollama")
    def test_short_transcript_ollama_fails_gemini_primary_fails_gemini_secondary_succeeds(
        self, mock_ollama, mock_gemini, mock_openrouter
    ):
        """Short transcript: Ollama fails -> Gemini primary fails -> Gemini secondary succeeds."""
        env = {
            "GEMINI_API_KEY": "test-gemini-key",
            "GEMINI_PRIMARY_MODEL": "gemini-3.7-flash",
            "GEMINI_FALLBACK_MODEL": "gemini-3.6-flash",
            "OPENROUTER_API_KEY": "test-or-key",
            "LLM_SHORT_MAX_WORDS": "1600",
            "LLM_MEDIUM_MAX_WORDS": "2500",
        }

        mock_ollama.side_effect = Exception("Ollama connection refused")
        mock_gemini.side_effect = [
            Exception("503 UNAVAILABLE"),
            ("Refined text Gemini 3.6", "Description"),
        ]

        short_transcript = "word " * 500

        with patch.dict(os.environ, env, clear=True):
            results = analyze_transcript_by_length(
                transcript=short_transcript,
                ollama_model="gemma4:26b",
                ollama_base_url="http://localhost:11434",
                output_language="Polish",
                category="Fitness",
            )

        self.assertIn("cloud", results)
        self.assertEqual(results["cloud"]["model_name"], "gemini-3.6-flash")
        self.assertEqual(mock_gemini.call_count, 2)
        mock_openrouter.assert_not_called()
