"""
LLM Strategy implementations for transcript analysis.
This module implements the Strategy Pattern for different LLM providers.
"""

import os
import time
from abc import ABC, abstractmethod

import google.generativeai as genai
import requests

from yt2md.chunking import ChunkingStrategyFactory

# Category-specific prompt additions
CATEGORY_PROMPTS = {
    "IT": "- Adding code examples in C# when it's possible\n - Write diagram in mermaid syntax when it can help understand discussed subject. Do not use quotes in node labels.",
    "Crypto": "- Write diagram in mermaid syntax when it can help understand discussed subject. Do not use quotes in node labels.\n- Highlighting key price levels and market indicators mentioned\n- Including links to relevant blockchain explorers when specific transactions or contracts are discussed",
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
        """
        Process model response to extract description and clean up text.

        Args:
            text: The raw model response text
            is_first_chunk: Whether this is the first chunk of the response

        Returns:
            tuple[str, str]: Processed text and extracted description (or empty string if not first chunk)
        """
        description = ""

        # Only extract description from first chunk
        if is_first_chunk:
            lines = text.split("\n")
            # Find the first occurrence of description line
            description_index = -1
            for idx, line in enumerate(lines):
                if line.startswith("DESCRIPTION:") or line.startswith("OPIS:"):
                    description_index = idx
                    prefix = (
                        "DESCRIPTION:" if line.startswith("DESCRIPTION:") else "OPIS:"
                    )
                    description = line.replace(prefix, "").strip()
                    break

            # Remove all text before and including the description line if found
            if description_index != -1:
                text = "\n".join(lines[description_index + 1 :])

        return text, description


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
        model_name = kwargs.get("model_name", "gemini-1.5-pro")
        output_language = kwargs.get("output_language", "English")
        category = kwargs.get("category", "IT")
        chunking_strategy = kwargs.get("chunking_strategy", "word")
        chunk_size = kwargs.get("chunk_size", 25000)

        if not api_key:
            raise ValueError("Gemini API key is required")

        # Configure Gemini
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)

        # Get chunking strategy
        chunker = ChunkingStrategyFactory.get_strategy(
            chunking_strategy, chunk_size=chunk_size
        )
        chunks = chunker.chunk_text(transcript)

        # Process each chunk
        final_output = []
        previous_response = ""
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

            try:
                response = model.generate_content(full_prompt)
                text = response.text

                # Process the response text
                processed_text, chunk_description = self.process_model_response(
                    text, i == 0
                )

                # Save description only from the first chunk
                if i == 0 and chunk_description:
                    description = chunk_description

                previous_response = processed_text
                final_output.append(processed_text)

            except Exception as e:
                raise Exception(f"Gemini API error: {str(e)}")

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
        chunk_size = kwargs.get("chunk_size", 25000)

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
                    if response.status_code == 429 and attempt < max_retries - 1:
                        # If rate limited, wait and retry
                        wait_time = retry_delay * (attempt + 1)
                        print(
                            f"Perplexity API rate limit hit, retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        # Re-raise the exception if it's not a rate limit or we've exhausted retries
                        raise Exception(
                            f"Perplexity API error: {str(e)}, Response: {response.text}"
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
        chunk_size = kwargs.get("chunk_size", 10000)  # Default smaller for Ollama

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
        if chunks.__len__() > 1:
            print(
                f"Transcript is too long, splitting into {chunks.__len__()} chunks for processing."
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
