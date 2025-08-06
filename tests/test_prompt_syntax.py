"""
Tests for prompt template syntax validation.
These tests ensure that prompt templates are properly formatted and don't contain
syntax errors that could cause runtime failures.

These tests were created to prevent issues like:
1. CATEGORY_PROMPTS using sets instead of strings, causing formatting errors
2. Unescaped curly braces in templates causing KeyError exceptions
3. Trailing quotes breaking string formatting
4. Missing or invalid format placeholders

Running these tests regularly will catch template syntax issues before they reach production.
"""

import re
import unittest
from string import Formatter

from yt2md.llm_strategies import (
    CATEGORY_PROMPTS,
    FIRST_CHUNK_TEMPLATE,
    PROMPT_TEMPLATE,
)


class TestPromptSyntax(unittest.TestCase):
    """Test cases for prompt template syntax validation."""

    def test_category_prompts_structure(self):
        """Test that CATEGORY_PROMPTS has the correct structure."""
        # Ensure CATEGORY_PROMPTS is a dictionary
        self.assertIsInstance(CATEGORY_PROMPTS, dict)
        
        # Ensure all values are strings (not sets or other types)
        for category, prompts in CATEGORY_PROMPTS.items():
            with self.subTest(category=category):
                self.assertIsInstance(category, str)
                self.assertIsInstance(prompts, str)
                # Ensure prompts are not empty
                self.assertTrue(prompts.strip())

    def test_prompt_template_format_placeholders(self):
        """Test that PROMPT_TEMPLATE contains only valid format placeholders."""
        # Find all format placeholders in the template
        formatter = Formatter()
        placeholders = [field_name for _, field_name, _, _ in formatter.parse(PROMPT_TEMPLATE) if field_name]
        
        # Expected placeholders
        expected_placeholders = ['category_prompts', 'output_language']
        
        # Check that all placeholders are expected
        for placeholder in placeholders:
            with self.subTest(placeholder=placeholder):
                self.assertIn(placeholder, expected_placeholders, 
                             f"Unexpected placeholder '{placeholder}' found in PROMPT_TEMPLATE")
        
        # Check that all expected placeholders are present
        for expected in expected_placeholders:
            with self.subTest(expected=expected):
                self.assertIn(expected, placeholders,
                             f"Expected placeholder '{expected}' not found in PROMPT_TEMPLATE")

    def test_first_chunk_template_format_placeholders(self):
        """Test that FIRST_CHUNK_TEMPLATE contains only valid format placeholders."""
        # Find all format placeholders in the template
        formatter = Formatter()
        placeholders = [field_name for _, field_name, _, _ in formatter.parse(FIRST_CHUNK_TEMPLATE) if field_name]
        
        # Expected placeholders
        expected_placeholders = ['base_prompt']
        
        # Check that all placeholders are expected
        for placeholder in placeholders:
            with self.subTest(placeholder=placeholder):
                self.assertIn(placeholder, expected_placeholders,
                             f"Unexpected placeholder '{placeholder}' found in FIRST_CHUNK_TEMPLATE")
        
        # Check that all expected placeholders are present
        for expected in expected_placeholders:
            with self.subTest(expected=expected):
                self.assertIn(expected, placeholders,
                             f"Expected placeholder '{expected}' not found in FIRST_CHUNK_TEMPLATE")

    def test_prompt_template_formatting_with_category_prompts(self):
        """Test that PROMPT_TEMPLATE can be formatted with all category prompts."""
        for category, category_prompt in CATEGORY_PROMPTS.items():
            with self.subTest(category=category):
                try:
                    formatted = PROMPT_TEMPLATE.format(
                        category_prompts=category_prompt,
                        output_language="English"
                    )
                    # Ensure the template was actually formatted (not empty)
                    self.assertTrue(formatted.strip())
                    # Ensure category prompts were inserted
                    if category_prompt.strip():
                        self.assertIn(category_prompt, formatted)
                except Exception as e:
                    self.fail(f"Failed to format PROMPT_TEMPLATE with category '{category}': {e}")

    def test_first_chunk_template_formatting(self):
        """Test that FIRST_CHUNK_TEMPLATE can be formatted properly."""
        # Test with a sample base prompt
        base_prompt = "This is a test base prompt with {category_prompts} and {output_language}"
        
        try:
            formatted = FIRST_CHUNK_TEMPLATE.format(base_prompt=base_prompt)
            self.assertTrue(formatted.strip())
            self.assertIn("DESCRIPTION:", formatted)
            self.assertIn(base_prompt, formatted)
        except Exception as e:
            self.fail(f"Failed to format FIRST_CHUNK_TEMPLATE: {e}")

    def test_no_unescaped_curly_braces_in_prompt_template(self):
        """Test that PROMPT_TEMPLATE doesn't contain unescaped curly braces that would cause format errors."""
        # Find all single curly braces (not doubled for escaping)
        single_braces = re.findall(r'(?<!\{)\{(?!\{)[^}]*\}(?!\})', PROMPT_TEMPLATE)
        
        # Filter out valid placeholders
        formatter = Formatter()
        valid_placeholders = [f"{{{field_name}}}" for _, field_name, _, _ in formatter.parse(PROMPT_TEMPLATE) if field_name]
        
        # Check for invalid single braces
        invalid_braces = [brace for brace in single_braces if brace not in valid_placeholders]
        
        self.assertEqual([], invalid_braces,
                        f"Found unescaped curly braces in PROMPT_TEMPLATE: {invalid_braces}")

    def test_no_unescaped_curly_braces_in_first_chunk_template(self):
        """Test that FIRST_CHUNK_TEMPLATE doesn't contain unescaped curly braces."""
        # Find all single curly braces (not doubled for escaping)
        single_braces = re.findall(r'(?<!\{)\{(?!\{)[^}]*\}(?!\})', FIRST_CHUNK_TEMPLATE)
        
        # Filter out valid placeholders
        formatter = Formatter()
        valid_placeholders = [f"{{{field_name}}}" for _, field_name, _, _ in formatter.parse(FIRST_CHUNK_TEMPLATE) if field_name]
        
        # Check for invalid single braces
        invalid_braces = [brace for brace in single_braces if brace not in valid_placeholders]
        
        self.assertEqual([], invalid_braces,
                        f"Found unescaped curly braces in FIRST_CHUNK_TEMPLATE: {invalid_braces}")

    def test_full_template_integration(self):
        """Test the complete template formatting process as used in strategies."""
        for category in CATEGORY_PROMPTS.keys():
            with self.subTest(category=category):
                # Get category-specific prompts
                category_prompt = CATEGORY_PROMPTS.get(category, "")
                
                # Prepare base prompt (as done in strategies)
                try:
                    base_prompt = PROMPT_TEMPLATE.format(
                        category_prompts=category_prompt,
                        output_language="English"
                    )
                    self.assertTrue(base_prompt.strip())
                except Exception as e:
                    self.fail(f"Failed to format base prompt for category '{category}': {e}")
                
                # Prepare first chunk prompt (as done in strategies)
                try:
                    first_chunk_prompt = FIRST_CHUNK_TEMPLATE.format(base_prompt=base_prompt)
                    self.assertTrue(first_chunk_prompt.strip())
                    self.assertIn("DESCRIPTION:", first_chunk_prompt)
                    self.assertIn(base_prompt, first_chunk_prompt)
                except Exception as e:
                    self.fail(f"Failed to format first chunk prompt for category '{category}': {e}")

    def test_template_content_validity(self):
        """Test that templates contain expected content and structure."""
        # Check PROMPT_TEMPLATE contains key instructions
        expected_instructions = [
            "well-structured",
            "readable format",
            "retaining EVERY detail",
            "Organizing the content",
            "bullet points",
            "Mermaid syntax",
            "Markdown table syntax"
        ]
        
        for instruction in expected_instructions:
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, PROMPT_TEMPLATE,
                             f"Expected instruction '{instruction}' not found in PROMPT_TEMPLATE")
        
        # Check FIRST_CHUNK_TEMPLATE contains description request
        self.assertIn("DESCRIPTION:", FIRST_CHUNK_TEMPLATE)
        self.assertIn("one-sentence description", FIRST_CHUNK_TEMPLATE)

    def test_category_prompts_content_validity(self):
        """Test that category prompts contain valid content."""
        # Test IT category
        if "IT" in CATEGORY_PROMPTS:
            it_prompt = CATEGORY_PROMPTS["IT"]
            self.assertIn("C#", it_prompt)
            self.assertIn("code examples", it_prompt)
        
        # Test Crypto category
        if "Crypto" in CATEGORY_PROMPTS:
            crypto_prompt = CATEGORY_PROMPTS["Crypto"]
            self.assertIn("price levels", crypto_prompt)
            self.assertIn("blockchain explorers", crypto_prompt)

    def test_no_trailing_quotes_in_templates(self):
        """Test that templates don't contain problematic trailing quotes."""
        # Check for lines ending with stray quotes that could break formatting
        problematic_patterns = [
            r'[^"]",\s*$',  # Lines ending with quote-comma
            r'[^"]\.",\s*$',  # Lines ending with period-quote-comma
        ]
        
        templates = {
            "PROMPT_TEMPLATE": PROMPT_TEMPLATE,
            "FIRST_CHUNK_TEMPLATE": FIRST_CHUNK_TEMPLATE
        }
        
        for template_name, template_content in templates.items():
            lines = template_content.split('\n')
            for i, line in enumerate(lines, 1):
                for pattern in problematic_patterns:
                    if re.search(pattern, line):
                        self.fail(f"Found problematic trailing quote in {template_name} at line {i}: {line.strip()}")

    def test_escaped_braces_in_content(self):
        """Test that curly braces in content are properly escaped."""
        # Check that literal curly braces in content are doubled
        content_with_braces = "curly braces {{ }}"
        
        # This should be in the PROMPT_TEMPLATE as escaped braces
        self.assertIn("{{ }}", PROMPT_TEMPLATE,
                     "Literal curly braces should be escaped with double braces in PROMPT_TEMPLATE")

    def test_output_language_placeholder_usage(self):
        """Test that output_language placeholder is used correctly."""
        # Ensure the placeholder appears in a meaningful context
        self.assertIn("entirely in {output_language}", PROMPT_TEMPLATE)
        
        # Test formatting with different languages
        test_languages = ["English", "Polish", "Spanish", "French"]
        
        for language in test_languages:
            with self.subTest(language=language):
                formatted = PROMPT_TEMPLATE.format(
                    category_prompts=CATEGORY_PROMPTS.get("IT", ""),
                    output_language=language
                )
                self.assertIn(f"entirely in {language}", formatted)


if __name__ == "__main__":
    unittest.main()
