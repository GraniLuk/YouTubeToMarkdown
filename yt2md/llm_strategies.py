"""
LLM Strategy implementations for transcript analysis.
This module implements the Strategy Pattern for different LLM providers.
"""

import os
import random
import time
from abc import ABC, abstractmethod

import requests
from google import genai
from google.genai import types

from yt2md import response_processing
from yt2md.chunking import ChunkingStrategyFactory
from yt2md.logger import get_logger

logger = get_logger("llm_strategies")

# Category-specific prompt additions
CATEGORY_PROMPTS = {
    "IT": "- Add code examples in C# when possible.",
    "Crypto": (
        "- Highlighting key price levels and market indicators mentioned.\n"
        "- Including links to relevant blockchain explorers when specific transactions or contracts are discussed."
    ),
}

# Main prompt template shared across all strategies
PROMPT_TEMPLATE = """
Turn the following unorganized text into a well-structured, readable format while retaining EVERY detail, context, and nuance of the original content.
Refine the text to improve clarity, grammar, and coherence WITHOUT cutting, summarizing, or omitting any information.
The goal is to make the content easier to read and process by:

- Organizing the content into logical sections with appropriate subheadings.
- Using bullet points or numbered lists where applicable to present facts, stats, or comparisons.
- Highlighting key terms, names, or headings with bold text for emphasis.
- Preserving the original tone, humor, and narrative style while ensuring readability.
- Adding clear separators or headings for topic shifts to improve navigation.
- For diagrams (e.g., flowcharts, sequences, timelines, or entity relationships), use Mermaid syntax. Do not use quotes in node labels.
- For node labels in Mermaid diagrams: Enclose the label in double quotes inside the brackets if it contains special characters such as parentheses ( ), brackets [ ], curly braces {{ }}, semicolons ;, or any punctuation/symbols that might break the syntax. Otherwise, do not use quotes to keep the syntax simple. Example: Use A[Simple Label] for basic text, but B[""Complex (with parens)""] for labels with special characters.
- For tables (e.g., data grids or comparisons), use standard Markdown table syntax with proper headers and filled cells.
- Only create a table or diagram if it genuinely helps explain the subject; keep it concise and relevant.
{category_prompts}

Ensure the text remains informative, capturing the original intent, tone,
and details while presenting the information in a format optimized for analysis by both humans and AI.
REMEMBER that Details are important, DO NOT overlook Any details, even small ones.
All output must be generated entirely in {output_language}. Do not use any other language at any point in the response.
Text:
"""

# First chunk template (with description request) for strategies that need it
FIRST_CHUNK_TEMPLATE = """
First, provide a one-sentence description of the content (start with "DESCRIPTION:").
Then, {base_prompt}
"""


class LLMStrategy(ABC):
    """Abstract base class for LLM processing strategies."""

    @abstractmethod
    def analyze_transcript(self, transcript: str, **kwargs) -> tuple[str, str]:
        """
        Analyze the given transcript and return a tuple of (refined_text, description).

        Args:
            transcript: The input text transcript to analyze
            **kwargs: Additional strategy-specific parameters

        Returns:
            tuple[str, str]: Refined text and description
        """
        pass

    @staticmethod
    def process_model_response(text: str, is_first_chunk: bool) -> tuple[str, str]:
        """Backward-compatible wrapper delegating to yt2md.response_processing.process_model_response."""
        return response_processing.process_model_response(text, is_first_chunk)


class GeminiStrategy(LLMStrategy):
    """Gemini LLM implementation strategy."""

    def analyze_transcript(self, transcript: str, **kwargs) -> tuple[str, str]:
        """
        Analyze transcript using Gemini API.

        Args:
            transcript: Input transcript text
            **kwargs: Must include api_key, may include model_name, output_language, and category

        Returns:
            tuple[str, str]: Refined text and description
        """
        api_key = kwargs.get("api_key")
        model_name = kwargs.get("model_name")
        output_language = kwargs.get("output_language", "English")
        category = kwargs.get("category", "IT")
        chunking_strategy = kwargs.get("chunking_strategy", "word")
        chunk_size = kwargs.get("chunk_size", 5000)
        logger.debug(
            f"Using Gemini strategy with model: {model_name}, output language: {output_language}, category: {category}, chunking strategy: {chunking_strategy}, chunk size: {chunk_size}"
        )

        if not api_key:
            raise ValueError("Gemini API key is required")

        if not model_name:
            raise ValueError("Gemini model name is required")

        # Configure Gemini client
        client = genai.Client(api_key=api_key)

        # Fixed retry configuration (no external configurability)
        max_retries = 4
        base_backoff = 2.5
        max_backoff = 14.0
        jitter = 0.3  # proportion of backoff added/subtracted

        def _is_retryable_error(exc: Exception) -> bool:
            msg = str(exc).lower()
            # Gemini overloaded / transient indicators
            return any(
                token in msg
                for token in [
                    "503",  # service unavailable
                    "unavailable",
                    "rate limit",  # generic rate limit phrase
                    "429",  # too many requests
                    "deadline exceeded",
                    "temporarily",  # temporarily unavailable
                ]
            )

        def _compute_backoff(attempt: int) -> float:
            # attempt starts at 1
            sleep = min((base_backoff ** (attempt - 1)), max_backoff)
            if jitter > 0:
                delta = sleep * jitter
                sleep = random.uniform(max(0, sleep - delta), sleep + delta)
            return sleep

        # Get chunking strategy
        chunker = ChunkingStrategyFactory.get_strategy(
            chunking_strategy, chunk_size=chunk_size
        )
        chunks = chunker.chunk_text(transcript)

        # Process each chunk
        final_output = []
        previous_interaction_id = None
        description = "No description available"

        # Get category-specific prompts
        category_prompt = CATEGORY_PROMPTS.get(category, "")

        # Prepare base prompt
        base_prompt = PROMPT_TEMPLATE.format(
            category_prompts=category_prompt, output_language=output_language
        )

        # Prepare first chunk prompt with description request
        first_chunk_prompt = FIRST_CHUNK_TEMPLATE.format(base_prompt=base_prompt)

        for i, chunk in enumerate(chunks):
            # Prepare prompt with context if needed
            if previous_interaction_id:
                context_prompt = (
                    "The following text is a continuation of the previous transcript chunk. "
                    "Process it maintaining consistency with the previous output. "
                    "New text to process:\n"
                )
            else:
                context_prompt = ""

            # Use different template for first chunk
            template = first_chunk_prompt if i == 0 else base_prompt

            # Create full prompt
            full_prompt = f"{context_prompt}{template}\n\n{chunk}"

            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    kwargs_interactions = {
                        "model": model_name,
                        "input": full_prompt,
                        "generation_config": types.GenerateContentConfig(
                            temperature=0.6,
                            max_output_tokens=60000,
                        ),
                    }
                    if previous_interaction_id:
                        kwargs_interactions["previous_interaction_id"] = (
                            previous_interaction_id
                        )

                    response = client.interactions.create(**kwargs_interactions)

                    # Store interaction ID for next chunk
                    if hasattr(response, "id") and response.id:
                        previous_interaction_id = response.id

                    # Extract text from outputs
                    text = ""
                    if hasattr(response, "outputs") and response.outputs:
                        for output in response.outputs:
                            if hasattr(output, "text") and output.text:
                                text += output.text
                    processed_text, chunk_description = self.process_model_response(
                        text, i == 0
                    )
                    if i == 0 and chunk_description:
                        description = chunk_description

                    final_output.append(processed_text)
                    if attempt > 1:
                        logger.info(
                            f"Gemini chunk {i + 1}/{len(chunks)} succeeded after {attempt} attempts"
                        )
                    break
                except Exception as e:  # noqa: BLE001
                    last_error = e
                    if attempt < max_retries and _is_retryable_error(e):
                        sleep_for = _compute_backoff(attempt)
                        logger.warning(
                            f"Gemini transient error (attempt {attempt}/{max_retries}): {e}. Retrying in {sleep_for:.2f}s"
                        )
                        time.sleep(sleep_for)
                        continue
                    # Non-retryable or exhausted retries
                    logger.error(
                        f"Gemini API error (attempt {attempt}/{max_retries}) for chunk {i + 1}: {e}"
                    )
                    raise Exception(f"Gemini API error: {str(e)}") from e
            else:  # pragma: no cover - defensive, loop should break or raise
                raise Exception(
                    f"Gemini API failed after {max_retries} attempts: {last_error}"
                )

        return "\n\n".join(final_output), description


class PerplexityStrategy(LLMStrategy):
    """Perplexity AI implementation strategy."""

    def analyze_transcript(self, transcript: str, **kwargs) -> tuple[str, str]:
        """
        Analyze transcript using Perplexity API.

        Args:
            transcript: Input transcript text
            **kwargs: Must include api_key, may include model_name, output_language, and category

        Returns:
            tuple[str, str]: Refined text and description
        """
        api_key = kwargs.get("api_key")
        model_name = kwargs.get("model_name", "sonar-pro")
        output_language = kwargs.get("output_language", "English")
        category = kwargs.get("category", "IT")
        max_retries = kwargs.get("max_retries", 3)
        retry_delay = kwargs.get("retry_delay", 2)
        chunking_strategy = kwargs.get("chunking_strategy", "word")
        chunk_size = kwargs.get("chunk_size", 5000)

        if not api_key:
            raise ValueError("Perplexity API key is required")

        # Get category-specific prompts
        category_prompt = CATEGORY_PROMPTS.get(category, "")

        # Prepare base prompt
        base_prompt = PROMPT_TEMPLATE.format(
            category_prompts=category_prompt, output_language=output_language
        )

        # Prepare first chunk prompt with description request
        first_chunk_prompt = FIRST_CHUNK_TEMPLATE.format(base_prompt=base_prompt)

        url = "https://api.perplexity.ai/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Get chunking strategy
        chunker = ChunkingStrategyFactory.get_strategy(
            chunking_strategy, chunk_size=chunk_size
        )
        chunks = chunker.chunk_text(transcript)

        # Process each chunk
        final_output = []
        previous_response = ""
        description = "No description available"

        for i, chunk in enumerate(chunks):
            # Prepare prompt with context if needed
            if previous_response:
                context_prompt = (
                    "The following text is a continuation... "
                    f"Previous response:\n{previous_response}\n\nNew text to process(Do Not Repeat the Previous response:):\n"
                )
            else:
                context_prompt = ""

            # Use different template for first chunk
            template = first_chunk_prompt if i == 0 else base_prompt

            # Create full prompt
            full_prompt = f"{context_prompt}{template}\n\n{chunk}"

            data = {
                "model": model_name,
                "messages": [{"role": "user", "content": full_prompt}],
                "temperature": 0.7,
                "max_tokens": 4000,
            }

            response = None
            for attempt in range(max_retries):
                try:
                    response = requests.post(url, json=data, headers=headers)
                    response.raise_for_status()

                    result = response.json()
                    text = result["choices"][0]["message"]["content"]

                    # Process the response text
                    processed_text, chunk_description = self.process_model_response(
                        text, i == 0
                    )

                    # Save description only from the first chunk
                    if i == 0 and chunk_description:
                        description = chunk_description

                    previous_response = processed_text
                    final_output.append(processed_text)
                    break

                except requests.exceptions.HTTPError as e:
                    if (
                        response is not None
                        and response.status_code == 429
                        and attempt < max_retries - 1
                    ):
                        # If rate limited, wait and retry
                        wait_time = retry_delay * (attempt + 1)
                        print(
                            f"Perplexity API rate limit hit, retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        # Re-raise the exception if it's not a rate limit or we've exhausted retries
                        response_text = (
                            response.text
                            if response is not None
                            else "No response text"
                        )
                        raise Exception(
                            f"Perplexity API error: {str(e)}, Response: {response_text}"
                        )

                except Exception as e:
                    raise Exception(f"Perplexity API error: {str(e)}")
            else:
                # This will execute if the for loop completes without a break statement
                raise Exception("Failed to get response after multiple retries")

        return "\n\n".join(final_output), description


class OllamaStrategy(LLMStrategy):
    """Ollama (local LLM) implementation strategy."""

    def analyze_transcript(self, transcript: str, **kwargs) -> tuple[str, str]:
        """
        Analyze transcript using local Ollama instance.

        Args:
            transcript: Input transcript text
            **kwargs: May include model_name, output_language, category, base_url

        Returns:
            tuple[str, str]: Refined text and description
        """

        # Use environment variables with kwargs as fallback
        model_name = kwargs.get("model_name", os.getenv("OLLAMA_MODEL", "gemma3:4b"))
        output_language = kwargs.get("output_language", "English")
        category = kwargs.get("category", "IT")
        chunking_strategy = kwargs.get("chunking_strategy", "word")
        chunk_size = kwargs.get(
            "chunk_size", 2500
        )  # Increased chunk size to better utilize 4096 context

        # For backward compatibility, check both host and base_url parameters
        base_url = kwargs.get(
            "base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        )

        max_retries = kwargs.get("max_retries", 3)
        retry_delay = kwargs.get("retry_delay", 2)

        # Get category-specific prompts
        category_prompt = CATEGORY_PROMPTS.get(category, "")

        # Prepare base prompt
        base_prompt = PROMPT_TEMPLATE.format(
            category_prompts=category_prompt, output_language=output_language
        )

        # Prepare first chunk prompt with description request
        first_chunk_prompt = FIRST_CHUNK_TEMPLATE.format(base_prompt=base_prompt)

        # Get chunking strategy
        chunker = ChunkingStrategyFactory.get_strategy(
            chunking_strategy, chunk_size=chunk_size
        )
        chunks = chunker.chunk_text(transcript)

        # Process each chunk
        final_output = []
        previous_response = ""
        description = "No description available"

        url = f"{base_url}/api/generate"
        if len(chunks) > 1:
            print(
                f"Transcript is too long, splitting into {len(chunks)} chunks for processing."
            )
        for i, chunk in enumerate(chunks):
            # Prepare prompt with context if needed
            if previous_response:
                context_prompt = (
                    "The following text is a continuation... "
                    f"Previous response:\n{previous_response}\n\nNew text to process(Do Not Repeat the Previous response:):\n"
                )
            else:
                context_prompt = ""

            # Use different template for first chunk
            template = first_chunk_prompt if i == 0 else base_prompt

            # Create full prompt
            full_prompt = f"{context_prompt}{template}\n\n{chunk}"

            data = {"model": model_name, "prompt": full_prompt, "stream": False}

            for attempt in range(max_retries):
                try:
                    response = requests.post(url, json=data)
                    response.raise_for_status()

                    result = response.json()
                    text = result.get("response", "")

                    # Process the response text
                    processed_text, chunk_description = self.process_model_response(
                        text, i == 0
                    )

                    # Save description only from the first chunk
                    if i == 0 and chunk_description:
                        description = chunk_description

                    previous_response = processed_text
                    final_output.append(processed_text)
                    break

                except requests.exceptions.RequestException as e:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        print(f"Ollama API error, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        raise Exception(f"Ollama API error: {str(e)}")

                except Exception as e:
                    raise Exception(f"Ollama API error: {str(e)}")
            else:
                # This will execute if the for loop completes without a break statement
                raise Exception("Failed to get response after multiple retries")

        return "\n\n".join(final_output), description


class LLMFactory:
    """Factory class to create LLM strategies based on provider name."""

    @staticmethod
    def get_strategy(provider: str) -> LLMStrategy:
        """
        Get the appropriate LLM strategy based on provider name.

        Args:
            provider: The name of the LLM provider ("gemini", "perplexity", "ollama")

        Returns:
            LLMStrategy: The corresponding strategy implementation
        """
        strategies = {
            "gemini": GeminiStrategy(),
            "perplexity": PerplexityStrategy(),
            "ollama": OllamaStrategy(),
        }

        strategy = strategies.get(provider.lower())
        if not strategy:
            raise ValueError(f"Unknown LLM provider: {provider}")

        return strategy
