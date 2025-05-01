"""
Tests for the LLM strategies module.
"""

import unittest

from yt2md.llm_strategies import LLMStrategy


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


if __name__ == "__main__":
    unittest.main()
