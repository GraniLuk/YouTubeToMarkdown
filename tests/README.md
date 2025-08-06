# Test Suite for YouTubeToMarkdown

This directory contains comprehensive tests for the YouTubeToMarkdown application, with a focus on preventing prompt template syntax issues that could cause runtime failures.

## Test Files

### `test_llm_strategies.py`
Original tests for the LLM strategy implementations, focusing on the core logic and response processing.

### `test_prompt_syntax.py` 
**NEW**: Comprehensive syntax validation tests for prompt templates. These tests prevent issues like:
- Category prompts using sets instead of strings
- Unescaped curly braces causing KeyError exceptions  
- Trailing quotes breaking string formatting
- Missing or invalid format placeholders
- Malformed template structures

### `test_prompt_integration.py`
**NEW**: Integration tests that simulate the complete prompt formatting workflow used by LLM strategies. These tests:
- Verify end-to-end prompt preparation
- Test with different languages and categories
- Include regression tests for known issues
- Validate prompt length limits and content

## Running Tests

Run all tests:
```bash
python -m pytest tests/ -v
```

Run specific test files:
```bash
python -m pytest tests/test_prompt_syntax.py -v
python -m pytest tests/test_prompt_integration.py -v
```

## Test Coverage

The test suite now covers:
- ✅ Prompt template syntax validation
- ✅ Category prompt structure validation
- ✅ Template formatting with all categories and languages
- ✅ Edge cases and error conditions
- ✅ Regression tests for known issues
- ✅ Integration testing of the complete prompt workflow
- ✅ LLM strategy response processing

## Why These Tests Matter

The prompt syntax tests were added after a production issue where:
1. `CATEGORY_PROMPTS` was incorrectly structured as sets instead of strings
2. Template formatting failed with `KeyError` exceptions
3. Both Gemini and Perplexity APIs returned empty responses
4. The application appeared to work but produced no useful output

These tests ensure such issues are caught during development rather than in production.
