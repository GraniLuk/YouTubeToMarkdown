"""
Integration tests that verify the complete prompt formatting workflow.
These tests simulate the exact operations that the LLM strategies perform,
ensuring that all template formatting works correctly in the real-world usage scenario.
"""

import unittest

from yt2md.llm_strategies import (
    CATEGORY_PROMPTS,
    FIRST_CHUNK_TEMPLATE,
    PROMPT_TEMPLATE,
    LLMFactory,
)


class TestPromptIntegration(unittest.TestCase):
    """Integration tests for prompt template usage in strategies."""

    def test_gemini_strategy_prompt_preparation(self):
        """Test that GeminiStrategy can prepare prompts without errors."""
        # This test simulates the exact prompt preparation process from GeminiStrategy
        for category in CATEGORY_PROMPTS.keys():
            with self.subTest(category=category):
                # Simulate the exact process from GeminiStrategy.analyze_transcript
                category_prompt = CATEGORY_PROMPTS.get(category, "")
                output_language = "English"
                
                # Prepare base prompt (as done in GeminiStrategy)
                try:
                    base_prompt = PROMPT_TEMPLATE.format(
                        category_prompts=category_prompt, 
                        output_language=output_language
                    )
                except Exception as e:
                    self.fail(f"Failed to format base prompt for category '{category}': {e}")
                
                # Prepare first chunk prompt (as done in GeminiStrategy)
                try:
                    first_chunk_prompt = FIRST_CHUNK_TEMPLATE.format(base_prompt=base_prompt)
                except Exception as e:
                    self.fail(f"Failed to format first chunk prompt for category '{category}': {e}")
                
                # Verify the prompts are not empty
                self.assertTrue(base_prompt.strip())
                self.assertTrue(first_chunk_prompt.strip())
                
                # Verify that category prompts are included if they exist
                if category_prompt.strip():
                    self.assertIn(category_prompt, base_prompt)

    def test_factory_strategy_creation(self):
        """Test that the LLMFactory can create strategies without issues."""
        providers = ["gemini", "perplexity", "ollama"]
        
        for provider in providers:
            with self.subTest(provider=provider):
                try:
                    strategy = LLMFactory.get_strategy(provider)
                    self.assertIsNotNone(strategy)
                except Exception as e:
                    self.fail(f"Failed to create strategy for provider '{provider}': {e}")

    def test_prompt_with_different_languages(self):
        """Test prompt formatting with various output languages."""
        test_languages = ["English", "Polish", "Spanish", "French", "German", "Italian"]
        
        for language in test_languages:
            with self.subTest(language=language):
                try:
                    # Test with IT category
                    category_prompt = CATEGORY_PROMPTS.get("IT", "")
                    base_prompt = PROMPT_TEMPLATE.format(
                        category_prompts=category_prompt,
                        output_language=language
                    )
                    first_chunk_prompt = FIRST_CHUNK_TEMPLATE.format(base_prompt=base_prompt)
                    
                    # Verify language is correctly inserted
                    self.assertIn(language, base_prompt)
                    self.assertIn(language, first_chunk_prompt)
                    
                except Exception as e:
                    self.fail(f"Failed to format prompts with language '{language}': {e}")

    def test_prompt_with_edge_case_categories(self):
        """Test prompt formatting with edge cases and empty categories."""
        edge_cases = [
            ("", ""),  # Empty category and prompt
            ("NonExistent", ""),  # Non-existent category
            ("TestCategory", "- This is a test prompt with special chars: {}[]();"),  # Special characters
        ]
        
        for category, expected_prompt in edge_cases:
            with self.subTest(category=category):
                try:
                    category_prompt = CATEGORY_PROMPTS.get(category, expected_prompt)
                    base_prompt = PROMPT_TEMPLATE.format(
                        category_prompts=category_prompt,
                        output_language="English"
                    )
                    first_chunk_prompt = FIRST_CHUNK_TEMPLATE.format(base_prompt=base_prompt)
                    
                    # Should not crash and should produce valid output
                    self.assertIsInstance(base_prompt, str)
                    self.assertIsInstance(first_chunk_prompt, str)
                    
                except Exception as e:
                    self.fail(f"Failed to format prompts with edge case category '{category}': {e}")

    def test_prompt_length_limits(self):
        """Test that prompts don't become excessively long."""
        # This helps catch issues where template formatting might cause infinite loops or excessive content
        for category in CATEGORY_PROMPTS.keys():
            with self.subTest(category=category):
                category_prompt = CATEGORY_PROMPTS.get(category, "")
                base_prompt = PROMPT_TEMPLATE.format(
                    category_prompts=category_prompt,
                    output_language="English"
                )
                first_chunk_prompt = FIRST_CHUNK_TEMPLATE.format(base_prompt=base_prompt)
                
                # Reasonable length limits (adjust as needed)
                MAX_BASE_PROMPT_LENGTH = 10000  # 10KB
                MAX_FIRST_CHUNK_LENGTH = 15000  # 15KB
                
                self.assertLess(len(base_prompt), MAX_BASE_PROMPT_LENGTH,
                               f"Base prompt too long for category '{category}': {len(base_prompt)} chars")
                self.assertLess(len(first_chunk_prompt), MAX_FIRST_CHUNK_LENGTH,
                               f"First chunk prompt too long for category '{category}': {len(first_chunk_prompt)} chars")

    def test_prompt_contains_required_elements(self):
        """Test that formatted prompts contain all required elements."""
        category = "IT"
        category_prompt = CATEGORY_PROMPTS.get(category, "")
        
        base_prompt = PROMPT_TEMPLATE.format(
            category_prompts=category_prompt,
            output_language="English"
        )
        first_chunk_prompt = FIRST_CHUNK_TEMPLATE.format(base_prompt=base_prompt)
        
        # Check base prompt elements
        required_base_elements = [
            "well-structured",
            "readable format", 
            "EVERY detail",
            "English",  # output language
            "Text:"  # prompt ending
        ]
        
        for element in required_base_elements:
            with self.subTest(element=element):
                self.assertIn(element, base_prompt)
        
        # Check first chunk prompt elements
        required_first_chunk_elements = [
            "DESCRIPTION:",
            "one-sentence description",
            "well-structured",  # Should include base prompt
        ]
        
        for element in required_first_chunk_elements:
            with self.subTest(element=element):
                self.assertIn(element, first_chunk_prompt)

    def test_regression_category_prompts_not_sets(self):
        """Regression test: Ensure category prompts are strings, not sets."""
        # This would have caught the original bug where CATEGORY_PROMPTS contained sets
        for category, prompts in CATEGORY_PROMPTS.items():
            with self.subTest(category=category):
                self.assertIsInstance(prompts, str,
                                    f"Category prompt for '{category}' should be a string, not {type(prompts)}")
                # Additional check: ensure it's not a set converted to string
                self.assertNotRegex(prompts, r"^{.*}$",
                                   f"Category prompt for '{category}' looks like a set converted to string")

    def test_regression_no_stray_quotes(self):
        """Regression test: Ensure no stray quotes that could break formatting."""
        # This would have caught the original trailing quotes issue
        
        # Check for problematic quote patterns
        problematic_lines = []
        
        for line_num, line in enumerate(PROMPT_TEMPLATE.split('\n'), 1):
            # Look for lines ending with quote-comma patterns
            if line.strip().endswith('",') and not line.strip().endswith('""",'):
                problematic_lines.append(f"Line {line_num}: {line.strip()}")
        
        self.assertEqual([], problematic_lines,
                        f"Found lines with problematic trailing quotes in PROMPT_TEMPLATE: {problematic_lines}")


if __name__ == "__main__":
    unittest.main()
