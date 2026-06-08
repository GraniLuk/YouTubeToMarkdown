"""
Tests for transcript length threshold configuration.
"""

import os
import unittest
from unittest.mock import patch

from yt2md.config import get_transcript_length_category


class TestTranscriptLengthThresholds(unittest.TestCase):
    """Test transcript length categorization thresholds."""

    def test_default_thresholds_match_env_recommendation(self):
        """Built-in fallback keeps the former shared defaults."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("yt2md.config.get_llm_strategy_config", return_value={}):
                self.assertEqual(
                    get_transcript_length_category(1600, "Fitness"), "short"
                )
                self.assertEqual(
                    get_transcript_length_category(1601, "Fitness"), "medium"
                )
                self.assertEqual(
                    get_transcript_length_category(2501, "Fitness"), "long"
                )

    def test_env_thresholds_override_config(self):
        """Machine-local env thresholds should beat shared YAML config."""
        env = {
            "LLM_SHORT_MAX_WORDS": "10",
            "LLM_MEDIUM_MAX_WORDS": "20",
        }
        config = {"length_thresholds": {"short_max": 1600, "medium_max": 2500}}

        with patch.dict(os.environ, env, clear=True):
            with patch("yt2md.config.get_llm_strategy_config", return_value=config):
                self.assertEqual(
                    get_transcript_length_category(10, "Fitness"), "short"
                )
                self.assertEqual(
                    get_transcript_length_category(11, "Fitness"), "medium"
                )
                self.assertEqual(
                    get_transcript_length_category(21, "Fitness"), "long"
                )

    def test_config_thresholds_still_work_without_env(self):
        """YAML thresholds remain supported as a fallback."""
        config = {"length_thresholds": {"short_max": 5, "medium_max": 8}}

        with patch.dict(os.environ, {}, clear=True):
            with patch("yt2md.config.get_llm_strategy_config", return_value=config):
                self.assertEqual(
                    get_transcript_length_category(5, "Fitness"), "short"
                )
                self.assertEqual(
                    get_transcript_length_category(6, "Fitness"), "medium"
                )
                self.assertEqual(
                    get_transcript_length_category(9, "Fitness"), "long"
                )

    def test_invalid_env_thresholds_fall_back_to_defaults(self):
        """short threshold greater than medium threshold is ignored."""
        env = {
            "LLM_SHORT_MAX_WORDS": "3000",
            "LLM_MEDIUM_MAX_WORDS": "1000",
        }

        with patch.dict(os.environ, env, clear=True):
            with patch("yt2md.config.get_llm_strategy_config", return_value={}):
                self.assertEqual(
                    get_transcript_length_category(1600, "Fitness"), "short"
                )
                self.assertEqual(
                    get_transcript_length_category(2501, "Fitness"), "long"
                )


if __name__ == "__main__":
    unittest.main()
