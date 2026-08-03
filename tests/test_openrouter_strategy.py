"""
Tests for the OpenRouter LLM strategy.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from yt2md.llm_strategies import LLMFactory, OpenRouterStrategy


class TestOpenRouterStrategyFactory(unittest.TestCase):
    """Test that OpenRouterStrategy is properly registered in LLMFactory."""

    def test_factory_returns_openrouter_strategy(self):
        """LLMFactory.get_strategy('openrouter') returns an OpenRouterStrategy."""
        strategy = LLMFactory.get_strategy("openrouter")
        self.assertIsInstance(strategy, OpenRouterStrategy)

    def test_factory_case_insensitive(self):
        """Factory should handle case-insensitive provider names."""
        strategy = LLMFactory.get_strategy("OpenRouter")
        self.assertIsInstance(strategy, OpenRouterStrategy)

    def test_factory_unknown_provider_raises(self):
        """Factory should raise ValueError for unknown provider."""
        with self.assertRaises(ValueError):
            LLMFactory.get_strategy("unknown_provider")


class TestOpenRouterStrategyValidation(unittest.TestCase):
    """Test OpenRouterStrategy input validation."""

    def test_missing_api_key_raises(self):
        """Should raise ValueError when api_key is missing."""
        strategy = OpenRouterStrategy()
        with self.assertRaises(ValueError, msg="OpenRouter API key is required"):
            strategy.analyze_transcript("test transcript", api_key=None)

    def test_missing_api_key_empty_raises(self):
        """Should raise ValueError when api_key is empty string."""
        strategy = OpenRouterStrategy()
        with self.assertRaises(ValueError):
            strategy.analyze_transcript("test transcript", api_key="")


class TestOpenRouterStrategyAPICall(unittest.TestCase):
    """Test OpenRouterStrategy API call structure."""

    @patch("yt2md.llm_strategies.requests.post")
    def test_api_call_structure(self, mock_post):
        """Verify the API call uses correct URL, headers, and payload format."""
        # Mock a successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "DESCRIPTION: Test description\nProcessed content here"
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        strategy = OpenRouterStrategy()
        text, description = strategy.analyze_transcript(
            "test transcript",
            api_key="test-key-123",
            model_name="test/model:free",
            output_language="English",
            category="IT",
        )

        # Verify the call was made
        mock_post.assert_called_once()

        # Verify URL
        call_args = mock_post.call_args
        self.assertEqual(
            call_args[0][0] if call_args[0] else call_args[1].get("url"),
            "https://openrouter.ai/api/v1/chat/completions",
        )

        # Verify headers
        headers = call_args[1].get("headers", {})
        self.assertEqual(headers["Authorization"], "Bearer test-key-123")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertIn("HTTP-Referer", headers)
        self.assertIn("X-OpenRouter-Title", headers)

        # Verify payload structure
        payload = call_args[1].get("json", {})
        self.assertEqual(payload["model"], "test/model:free")
        self.assertIn("messages", payload)
        self.assertEqual(len(payload["messages"]), 1)
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertIn("temperature", payload)

        # Verify response processing
        self.assertEqual(description, "Test description")
        self.assertIn("Processed content here", text)

    @patch("yt2md.llm_strategies.requests.post")
    def test_successful_single_chunk(self, mock_post):
        """Test processing a short transcript (single chunk)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "DESCRIPTION: A test video\nRefined content"
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        strategy = OpenRouterStrategy()
        text, description = strategy.analyze_transcript(
            "short transcript",
            api_key="test-key",
            model_name="test/model",
        )

        self.assertEqual(description, "A test video")
        self.assertEqual(text, "Refined content")
        self.assertEqual(mock_post.call_count, 1)


class TestOpenRouterStrategyRetry(unittest.TestCase):
    """Test OpenRouterStrategy retry behavior."""

    @patch("yt2md.llm_strategies.time.sleep")
    @patch("yt2md.llm_strategies.requests.post")
    def test_retry_on_429(self, mock_post, mock_sleep):
        """Should retry on HTTP 429 (rate limit) responses."""
        # First call returns 429, second succeeds
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.text = "Rate limited"
        mock_429.raise_for_status.side_effect = __import__(
            "requests"
        ).exceptions.HTTPError(response=mock_429)

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "choices": [{"message": {"content": "DESCRIPTION: OK\nContent"}}]
        }
        mock_ok.raise_for_status = MagicMock()

        mock_post.side_effect = [mock_429, mock_ok]

        strategy = OpenRouterStrategy()
        text, description = strategy.analyze_transcript(
            "test transcript",
            api_key="test-key",
            model_name="test/model",
        )

        # Should have called twice (one retry)
        self.assertEqual(mock_post.call_count, 2)
        # Should have slept between retries
        mock_sleep.assert_called_once()
        self.assertEqual(description, "OK")

    @patch("yt2md.llm_strategies.time.sleep")
    @patch("yt2md.llm_strategies.requests.post")
    def test_retry_on_503(self, mock_post, mock_sleep):
        """Should retry on HTTP 503 (service unavailable) responses."""
        mock_503 = MagicMock()
        mock_503.status_code = 503
        mock_503.text = "Service Unavailable"
        mock_503.raise_for_status.side_effect = __import__(
            "requests"
        ).exceptions.HTTPError(response=mock_503)

        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "choices": [{"message": {"content": "DESCRIPTION: OK\nContent"}}]
        }
        mock_ok.raise_for_status = MagicMock()

        mock_post.side_effect = [mock_503, mock_ok]

        strategy = OpenRouterStrategy()
        text, description = strategy.analyze_transcript(
            "test transcript",
            api_key="test-key",
            model_name="test/model",
        )

        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once()

    @patch("yt2md.llm_strategies.requests.post")
    def test_non_retryable_error_raises_immediately(self, mock_post):
        """Should raise immediately on non-retryable HTTP errors (e.g., 400)."""
        mock_400 = MagicMock()
        mock_400.status_code = 400
        mock_400.text = "Bad Request"
        mock_400.raise_for_status.side_effect = __import__(
            "requests"
        ).exceptions.HTTPError(response=mock_400)

        mock_post.return_value = mock_400

        strategy = OpenRouterStrategy()
        with self.assertRaises(Exception) as ctx:
            strategy.analyze_transcript(
                "test transcript",
                api_key="test-key",
                model_name="test/model",
            )

        self.assertIn("OpenRouter", str(ctx.exception))
        # Should only have been called once (no retry)
        self.assertEqual(mock_post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
