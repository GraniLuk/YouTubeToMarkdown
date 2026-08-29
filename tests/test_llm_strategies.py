"""
Tests for the LLM strategies module.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

from yt2md.llm_strategies import LLMStrategy, OllamaStrategy


class TestLLMStrategy(unittest.TestCase):
    """Test cases for the LLMStrategy class."""

    def test_process_model_response_with_description_first_chunk(self):
        """Test processing a response with a description line in the first chunk."""
        text = (
            "DESCRIPTION: This is a test description\nSome content here\nMore content"
        )
        processed_text, description = LLMStrategy.process_model_response(
            text, is_first_chunk=True
        )

        self.assertEqual(description, "This is a test description")
        self.assertEqual(processed_text, "Some content here\nMore content")

    def test_process_model_response_without_description_first_chunk(self):
        """Test processing a response without a description line in the first chunk."""
        text = "Some content here\nMore content"
        processed_text, description = LLMStrategy.process_model_response(
            text, is_first_chunk=True
        )

        self.assertEqual(description, "")
        self.assertEqual(processed_text, text)

    def test_process_model_response_opis_description(self):
        """Test processing a response with 'OPIS:' prefix for description."""
        text = "OPIS: This is a test description in Polish\nSome content here\nMore content"
        processed_text, description = LLMStrategy.process_model_response(
            text, is_first_chunk=True
        )

        self.assertEqual(description, "This is a test description in Polish")
        self.assertEqual(processed_text, "Some content here\nMore content")

    def test_process_model_response_not_first_chunk(self):
        """Test processing a response that is not the first chunk (no description extraction)."""
        text = "DESCRIPTION: This should be ignored\nSome content here\nMore content"
        processed_text, description = LLMStrategy.process_model_response(
            text, is_first_chunk=False
        )

        self.assertEqual(description, "")
        self.assertEqual(processed_text, text)

    def test_process_model_response_empty_text(self):
        """Test processing an empty response."""
        text = ""
        processed_text, description = LLMStrategy.process_model_response(
            text, is_first_chunk=True
        )

        self.assertEqual(description, "")
        self.assertEqual(processed_text, "")

    def test_process_model_response_multiline_before_description(self):
        """Test processing a response with content before the description line."""
        text = "Some header\nAnother line\nDESCRIPTION: This is a description\nActual content starts here"
        processed_text, description = LLMStrategy.process_model_response(
            text, is_first_chunk=True
        )

        self.assertEqual(description, "This is a description")
        self.assertEqual(processed_text, "Actual content starts here")


class TestOllamaStrategy(unittest.TestCase):
    """Test cases for Ollama-specific request and context behavior."""

    @staticmethod
    def _mock_ollama_response(content: str):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"response": content}
        response.raise_for_status = MagicMock()
        return response

    def test_ollama_sends_explicit_num_ctx_option(self):
        """Ollama payload should include the configured context window."""
        with patch.dict(os.environ, {"OLLAMA_NUM_CTX": "4096"}, clear=True):
            with patch("yt2md.llm_strategies.get_llm_model_config", return_value={}):
                with patch("yt2md.llm_strategies.requests.post") as mock_post:
                    mock_post.return_value = self._mock_ollama_response(
                        "DESCRIPTION: Demo\nProcessed content"
                    )

                    strategy = OllamaStrategy()
                    text, description = strategy.analyze_transcript(
                        "short transcript",
                        model_name="gemma4:12b",
                        base_url="http://localhost:11434",
                        output_language="Polish",
                        category="Fitness",
                        max_retries=1,
                    )

        self.assertEqual(text, "Processed content")
        self.assertEqual(description, "Demo")

        payload = mock_post.call_args[1]["json"]
        self.assertEqual(payload["options"]["num_ctx"], 4096)
        self.assertIn("Return only the requested Markdown output", payload["system"])

    def test_ollama_env_overrides_config_for_machine_tuning(self):
        """Machine-specific env values should beat shared config defaults."""
        env = {
            "OLLAMA_NUM_CTX": "6144",
            "OLLAMA_CHUNK_TOKENS": "20",
            "OLLAMA_PREVIOUS_CONTEXT_TOKENS": "8",
            "OLLAMA_OVERLAP_TOKENS": "8",
            "OLLAMA_TEMPERATURE": "0.2",
            "OLLAMA_TOP_P": "0.8",
            "OLLAMA_TOP_K": "32",
            "OLLAMA_SYSTEM_PROMPT": "local machine system prompt",
            "OLLAMA_MAX_RETRIES": "1",
        }
        config = {
            "num_ctx": 8192,
            "chunk_tokens": 5000,
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 64,
            "system_prompt": "shared config system prompt",
        }
        transcript = (
            "Alpha beta gamma delta epsilon zeta eta theta. "
            "Iota kappa lambda mu nu xi omicron pi. "
            "Rho sigma tau upsilon phi chi psi omega."
        )

        with patch.dict(os.environ, env, clear=True):
            with patch("yt2md.llm_strategies.get_llm_model_config", return_value=config):
                with patch("yt2md.llm_strategies.requests.post") as mock_post:
                    mock_post.side_effect = [
                        self._mock_ollama_response("DESCRIPTION: Demo\nFirst"),
                        self._mock_ollama_response("Second"),
                        self._mock_ollama_response("Third"),
                    ]

                    strategy = OllamaStrategy()
                    strategy.analyze_transcript(
                        transcript,
                        model_name="gemma4:12b",
                        base_url="http://localhost:11434",
                        output_language="Polish",
                        category="Fitness",
                    )

        self.assertGreater(mock_post.call_count, 1)
        payload = mock_post.call_args_list[0][1]["json"]
        self.assertEqual(payload["system"], "local machine system prompt")
        self.assertEqual(payload["options"]["num_ctx"], 6144)
        self.assertEqual(payload["options"]["temperature"], 0.2)
        self.assertEqual(payload["options"]["top_p"], 0.8)
        self.assertEqual(payload["options"]["top_k"], 32)

    def test_ollama_continuation_context_is_bounded(self):
        """Later chunks should not receive the full previous response."""
        transcript = (
            "Alpha beta gamma delta epsilon zeta eta theta. "
            "Iota kappa lambda mu nu xi omicron pi. "
            "Rho sigma tau upsilon phi chi psi omega. "
            "Training nutrition sleep recovery mobility strength."
        )
        first_response = (
            "DESCRIPTION: Demo\n"
            "first-response-start "
            + " ".join(f"context{i}" for i in range(60))
            + " first-response-tail"
        )
        responses = [
            self._mock_ollama_response(first_response),
            self._mock_ollama_response("second chunk output"),
            self._mock_ollama_response("third chunk output"),
            self._mock_ollama_response("fourth chunk output"),
        ]

        with patch.dict(os.environ, {}, clear=True):
            with patch("yt2md.llm_strategies.get_llm_model_config", return_value={}):
                with patch("yt2md.llm_strategies.requests.post") as mock_post:
                    mock_post.side_effect = responses

                    strategy = OllamaStrategy()
                    strategy.analyze_transcript(
                        transcript,
                        model_name="gemma4:12b",
                        base_url="http://localhost:11434",
                        output_language="Polish",
                        category="Fitness",
                        max_retries=1,
                        num_ctx=4096,
                        chunk_size=20,
                        previous_context_tokens=8,
                        overlap_tokens=8,
                    )

        self.assertGreater(mock_post.call_count, 1)
        second_payload = mock_post.call_args_list[1][1]["json"]
        second_prompt = second_payload["prompt"]

        self.assertIn("Recent formatted output context", second_prompt)
        self.assertIn("Immediate previous transcript tail", second_prompt)
        self.assertNotIn("first-response-start", second_prompt)
        self.assertIn("first-response-tail", second_prompt)


class TestConfigEnvResolution(unittest.TestCase):
    """Test LLM model configuration resolution from environment variables."""

    def test_gemini_config_reads_env(self):
        """Gemini configuration should prioritize environment variables."""
        from yt2md.config import get_llm_model_config

        env = {
            "GEMINI_PRIMARY_MODEL": "gemini-custom-primary",
            "GEMINI_FALLBACK_MODEL": "gemini-custom-fallback",
            "GEMINI_THINKING_LEVEL": "high",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("yt2md.config._load_config", return_value={}):
                config = get_llm_model_config("gemini")
                self.assertEqual(config["primary_model"], "gemini-custom-primary")
                self.assertEqual(config["fallback_model"], "gemini-custom-fallback")
                self.assertEqual(config["thinking_level"], "high")

    def test_gemini_config_defaults(self):
        """Gemini configuration should fall back to standard defaults."""
        from yt2md.config import get_llm_model_config

        with patch.dict(os.environ, {}, clear=True):
            with patch("yt2md.config._load_config", return_value={}):
                config = get_llm_model_config("gemini")
                self.assertEqual(config["primary_model"], "gemini-3.6-flash")
                self.assertEqual(config["fallback_model"], "gemini-3.5-flash")
                self.assertEqual(config["thinking_level"], "none")

    def test_openrouter_config_reads_env(self):
        """OpenRouter configuration should prioritize environment variables."""
        from yt2md.config import get_llm_model_config

        env = {
            "OPENROUTER_MODEL": "custom/model:free",
            "OPENROUTER_BASE_URL": "https://custom.openrouter.ai/v1",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("yt2md.config._load_config", return_value={}):
                config = get_llm_model_config("openrouter")
                self.assertEqual(config["model_name"], "custom/model:free")
                self.assertEqual(config["base_url"], "https://custom.openrouter.ai/v1")

    def test_strategy_by_length_defaults_without_yaml_config(self):
        """Default strategy by length should be provided even when channels.yaml has no llm_strategies."""
        from yt2md.config import get_llm_strategy_for_transcript

        with patch.dict(os.environ, {}, clear=True):
            with patch("yt2md.config._load_config", return_value={}):
                short_strategy = get_llm_strategy_for_transcript("short text", "IT")
                self.assertEqual(short_strategy["primary"]["provider"], "ollama")
                self.assertEqual(short_strategy["fallback"]["provider"], "gemini")

                medium_words = " ".join(["word"] * 2000)
                med_strategy = get_llm_strategy_for_transcript(medium_words, "IT")
                self.assertEqual(med_strategy["primary"]["provider"], "gemini")
                self.assertEqual(med_strategy["fallback"]["provider"], "gemini")

                long_words = " ".join(["word"] * 3000)
                long_strategy = get_llm_strategy_for_transcript(long_words, "IT")
                self.assertEqual(long_strategy["primary"]["provider"], "gemini")
                self.assertEqual(long_strategy["fallback"]["provider"], "openrouter")


if __name__ == "__main__":
    unittest.main()
