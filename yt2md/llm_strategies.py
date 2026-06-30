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
from yt2md.chunking import (
    ChunkingStrategyFactory,
    clip_text_to_token_budget,
    estimate_token_count,
)
from yt2md.config import get_llm_model_config
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

OLLAMA_DEFAULT_NUM_CTX = 8192
OLLAMA_DEFAULT_PREVIOUS_CONTEXT_TOKENS = 700
OLLAMA_DEFAULT_OVERLAP_TOKENS = 220
OLLAMA_DEFAULT_TEMPERATURE = 1.0
OLLAMA_DEFAULT_TOP_P = 0.95
OLLAMA_DEFAULT_TOP_K = 64
OLLAMA_SYSTEM_PROMPT = (
    "You are a precise transcript formatter. Return only the requested Markdown "
    "output. Do not include analysis, hidden thinking, or notes about your process."
)


def _positive_int_setting(*values, default: int) -> int:
    for value in values:
        if value in (None, ""):
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return default


def _positive_float_setting(*values, default: float) -> float:
    for value in values:
        if value in (None, ""):
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return default


def _string_setting(*values, default: str) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return default


def _calculate_ollama_chunk_budget(
    *,
    num_ctx: int,
    base_prompt: str,
    first_chunk_prompt: str,
    previous_context_tokens: int,
    overlap_tokens: int,
    response_reserve_tokens: int = 0,
    context_reserve_tokens: int = 0,
    safety_reserve_tokens: int = 0,
    min_chunk_tokens: int = 0,
    max_chunk_tokens: int = 0,
) -> int:
    prompt_tokens = max(
        estimate_token_count(base_prompt), estimate_token_count(first_chunk_prompt)
    )
    response_reserve = response_reserve_tokens or min(
        max(1024, num_ctx // 3), 4096
    )
    context_reserve = context_reserve_tokens or min(
        previous_context_tokens + overlap_tokens + max(250, num_ctx // 50),
        max(300, num_ctx // 5),
    )
    safety_reserve = safety_reserve_tokens or max(128, num_ctx // 20)
    budget = (
        num_ctx
        - prompt_tokens
        - response_reserve
        - context_reserve
        - safety_reserve
    )

    min_budget = min_chunk_tokens or min(1200, max(500, num_ctx // 4))
    max_budget = max_chunk_tokens or max(min_budget, num_ctx // 2)
    max_budget = max(min_budget, max_budget)
    return max(min_budget, min(budget, max_budget))


def _build_ollama_continuation_context(
    *, rolling_context: str, previous_chunk_tail: str
) -> str:
    parts = [
        "Continuation context for consistency only. Do not repeat this context in the output."
    ]
    if rolling_context:
        parts.append(f"Recent formatted output context:\n{rolling_context}")
    if previous_chunk_tail:
        parts.append(f"Immediate previous transcript tail:\n{previous_chunk_tail}")
    parts.append("New transcript text to process:")
    return "\n\n".join(parts) + "\n"


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
        chunk_size = kwargs.get("chunk_size", 8000)

        # Get Gemini config for thinking level
        gemini_config = get_llm_model_config("gemini", category)
        thinking_level_str = gemini_config.get("thinking_level", "none").lower()

        # Map thinking level string to enum (using getattr for safety)
        thinking_level = None
        if thinking_level_str and thinking_level_str != "none":
            thinking_level_attr = thinking_level_str.upper()
            try:
                thinking_level = getattr(types.ThinkingLevel, thinking_level_attr)
                logger.debug(f"Using thinking level: {thinking_level_attr}")
            except AttributeError:
                available = [attr for attr in dir(types.ThinkingLevel) if not attr.startswith('_') and attr.isupper()]
                logger.warning(
                    f"Unknown thinking level '{thinking_level_str}'. "
                    f"Available: {', '.join(available)}"
                )

        logger.debug(
            f"Using Gemini strategy with model: {model_name}, output language: {output_language}, category: {category}, chunking strategy: {chunking_strategy}, chunk size: {chunk_size}, thinking level: {thinking_level_str}"
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
            # Check for quota exhaustion (should NOT retry, need fallback)
            if "quota" in msg or ("429" in msg and "quota" in msg):
                return False
            # Gemini overloaded / transient indicators (CAN retry)
            return any(
                token in msg
                for token in [
                    "503",  # service unavailable
                    "unavailable",
                    "rate limit",  # generic rate limit phrase (but not quota)
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
            if final_output:
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
                    # Build generation config - only include thinking_config if thinking_level is set
                    gen_config_params = {
                        "temperature": 0.6,
                        "max_output_tokens": 60000,
                    }
                    if thinking_level:
                        gen_config_params["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)

                    response = client.models.generate_content(
                        model=model_name,
                        contents=full_prompt,
                        config=types.GenerateContentConfig(**gen_config_params),
                    )

                    text = getattr(response, "text", "") or ""
                    if not text and hasattr(response, "candidates") and response.candidates:
                        for candidate in response.candidates:
                            content = getattr(candidate, "content", None)
                            parts = getattr(content, "parts", None)
                            if not parts:
                                continue
                            for part in parts:
                                part_text = getattr(part, "text", None)
                                if part_text:
                                    text += part_text

                    if not text:
                        raise ValueError("Gemini returned an empty response")

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
        chunk_size = kwargs.get("chunk_size", 8000)

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

        output_language = kwargs.get("output_language", "English")
        category = kwargs.get("category", "IT")
        ollama_config = get_llm_model_config("ollama", category)
        model_name = _string_setting(
            kwargs.get("model_name"),
            os.getenv("OLLAMA_MODEL"),
            ollama_config.get("model_name"),
            default="gemma4:26b",
        )
        chunking_strategy = _string_setting(
            kwargs.get("chunking_strategy"),
            os.getenv("OLLAMA_CHUNKING_STRATEGY"),
            ollama_config.get("chunking_strategy"),
            default="token",
        )
        model_key = model_name.lower()

        num_ctx = _positive_int_setting(
            kwargs.get("num_ctx"),
            os.getenv("OLLAMA_NUM_CTX"),
            ollama_config.get("num_ctx"),
            default=OLLAMA_DEFAULT_NUM_CTX,
        )
        previous_context_tokens = _positive_int_setting(
            kwargs.get("previous_context_tokens"),
            os.getenv("OLLAMA_PREVIOUS_CONTEXT_TOKENS"),
            ollama_config.get("previous_context_tokens"),
            default=OLLAMA_DEFAULT_PREVIOUS_CONTEXT_TOKENS,
        )
        overlap_tokens = _positive_int_setting(
            kwargs.get("overlap_tokens"),
            os.getenv("OLLAMA_OVERLAP_TOKENS"),
            ollama_config.get("overlap_tokens"),
            default=OLLAMA_DEFAULT_OVERLAP_TOKENS,
        )
        fixed_chunk_tokens = _positive_int_setting(
            kwargs.get("chunk_size"),
            os.getenv("OLLAMA_CHUNK_TOKENS"),
            os.getenv("OLLAMA_CHUNK_SIZE"),
            ollama_config.get("chunk_tokens"),
            ollama_config.get("chunk_size"),
            default=0,
        )
        response_reserve_tokens = _positive_int_setting(
            kwargs.get("response_reserve_tokens"),
            os.getenv("OLLAMA_RESPONSE_RESERVE_TOKENS"),
            ollama_config.get("response_reserve_tokens"),
            default=0,
        )
        context_reserve_tokens = _positive_int_setting(
            kwargs.get("context_reserve_tokens"),
            os.getenv("OLLAMA_CONTEXT_RESERVE_TOKENS"),
            ollama_config.get("context_reserve_tokens"),
            default=0,
        )
        safety_reserve_tokens = _positive_int_setting(
            kwargs.get("safety_reserve_tokens"),
            os.getenv("OLLAMA_SAFETY_RESERVE_TOKENS"),
            ollama_config.get("safety_reserve_tokens"),
            default=0,
        )
        min_chunk_tokens = _positive_int_setting(
            kwargs.get("min_chunk_tokens"),
            os.getenv("OLLAMA_MIN_CHUNK_TOKENS"),
            ollama_config.get("min_chunk_tokens"),
            default=0,
        )
        max_chunk_tokens = _positive_int_setting(
            kwargs.get("max_chunk_tokens"),
            os.getenv("OLLAMA_MAX_CHUNK_TOKENS"),
            ollama_config.get("max_chunk_tokens"),
            default=0,
        )
        temperature = _positive_float_setting(
            kwargs.get("temperature"),
            os.getenv("OLLAMA_TEMPERATURE"),
            ollama_config.get("temperature"),
            default=OLLAMA_DEFAULT_TEMPERATURE,
        )
        top_p = _positive_float_setting(
            kwargs.get("top_p"),
            os.getenv("OLLAMA_TOP_P"),
            ollama_config.get("top_p"),
            default=OLLAMA_DEFAULT_TOP_P,
        )
        top_k = _positive_int_setting(
            kwargs.get("top_k"),
            os.getenv("OLLAMA_TOP_K"),
            ollama_config.get("top_k"),
            default=OLLAMA_DEFAULT_TOP_K,
        )
        system_prompt = _string_setting(
            kwargs.get("system_prompt"),
            os.getenv("OLLAMA_SYSTEM_PROMPT"),
            ollama_config.get("system_prompt"),
            default=OLLAMA_SYSTEM_PROMPT,
        )

        base_url = _string_setting(
            kwargs.get("base_url"),
            kwargs.get("host"),
            os.getenv("OLLAMA_BASE_URL"),
            ollama_config.get("base_url"),
            default="http://localhost:11434",
        )

        max_retries = _positive_int_setting(
            kwargs.get("max_retries"),
            os.getenv("OLLAMA_MAX_RETRIES"),
            ollama_config.get("max_retries"),
            default=3,
        )
        retry_delay = _positive_int_setting(
            kwargs.get("retry_delay"),
            os.getenv("OLLAMA_RETRY_DELAY_SECONDS"),
            ollama_config.get("retry_delay_seconds"),
            default=2,
        )

        # Get category-specific prompts
        category_prompt = CATEGORY_PROMPTS.get(category, "")

        # Prepare base prompt
        base_prompt = PROMPT_TEMPLATE.format(
            category_prompts=category_prompt, output_language=output_language
        )

        # Prepare first chunk prompt with description request
        first_chunk_prompt = FIRST_CHUNK_TEMPLATE.format(base_prompt=base_prompt)

        if fixed_chunk_tokens:
            chunk_token_budget = fixed_chunk_tokens
        else:
            chunk_token_budget = _calculate_ollama_chunk_budget(
                num_ctx=num_ctx,
                base_prompt=base_prompt,
                first_chunk_prompt=first_chunk_prompt,
                previous_context_tokens=previous_context_tokens,
                overlap_tokens=overlap_tokens,
                response_reserve_tokens=response_reserve_tokens,
                context_reserve_tokens=context_reserve_tokens,
                safety_reserve_tokens=safety_reserve_tokens,
                min_chunk_tokens=min_chunk_tokens,
                max_chunk_tokens=max_chunk_tokens,
            )

        # Get chunking strategy
        chunker = ChunkingStrategyFactory.get_strategy(
            chunking_strategy,
            chunk_size=chunk_token_budget,
            max_tokens=chunk_token_budget,
        )
        chunks = chunker.chunk_text(transcript)

        # Process each chunk
        final_output = []
        rolling_context = ""
        previous_chunk_tail = ""
        description = "No description available"

        url = f"{base_url}/api/generate"
        if len(chunks) > 1:
            print(
                f"Transcript is too long, splitting into {len(chunks)} chunks for processing."
            )
        logger.info(
            f"Ollama context: num_ctx={num_ctx}, chunk_budget~{chunk_token_budget} tokens, chunks={len(chunks)}"
        )
        for i, chunk in enumerate(chunks):
            # Prepare prompt with context if needed
            if rolling_context or previous_chunk_tail:
                context_prompt = _build_ollama_continuation_context(
                    rolling_context=rolling_context,
                    previous_chunk_tail=previous_chunk_tail,
                )
            else:
                context_prompt = ""

            # Use different template for first chunk
            template = first_chunk_prompt if i == 0 else base_prompt

            # Create full prompt
            full_prompt = f"{template}\n\n{context_prompt}{chunk}"

            # Advanced configuration for Gemma 4 models
            if "gemma4" in model_key:
                data = {
                    "model": model_name,
                    "prompt": full_prompt,
                    "system": system_prompt,
                    "stream": False,
                    "options": {
                        "num_ctx": num_ctx,
                        "temperature": temperature,
                        "top_p": top_p,
                        "top_k": top_k,
                    },
                }
            else:
                data = {
                    "model": model_name,
                    "prompt": full_prompt,
                    "system": system_prompt,
                    "stream": False,
                    "options": {
                        "num_ctx": num_ctx,
                        "temperature": temperature,
                        "top_p": top_p,
                        "top_k": top_k,
                    },
                }

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

                    rolling_context = clip_text_to_token_budget(
                        processed_text,
                        previous_context_tokens,
                        from_end=True,
                    )
                    previous_chunk_tail = clip_text_to_token_budget(
                        chunk,
                        overlap_tokens,
                        from_end=True,
                    )
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


class OpenRouterStrategy(LLMStrategy):
    """OpenRouter API implementation strategy (OpenAI-compatible)."""

    def analyze_transcript(self, transcript: str, **kwargs) -> tuple[str, str]:
        """
        Analyze transcript using OpenRouter API.

        Args:
            transcript: Input transcript text
            **kwargs: Must include api_key, may include model_name, output_language, category,
                      base_url, max_retries, retry_delay, chunking_strategy, chunk_size

        Returns:
            tuple[str, str]: Refined text and description
        """
        api_key = kwargs.get("api_key")
        model_name = kwargs.get(
            "model_name",
            os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash-preview-04-17:free"),
        )
        output_language = kwargs.get("output_language", "English")
        category = kwargs.get("category", "IT")
        max_retries = kwargs.get("max_retries", 4)
        retry_delay = kwargs.get("retry_delay", 3)
        chunking_strategy = kwargs.get("chunking_strategy", "word")
        chunk_size = kwargs.get("chunk_size", 8000)
        base_url = kwargs.get(
            "base_url", "https://openrouter.ai/api/v1/chat/completions"
        )

        logger.debug(
            f"Using OpenRouter strategy with model: {model_name}, "
            f"output language: {output_language}, category: {category}, "
            f"chunking strategy: {chunking_strategy}, chunk size: {chunk_size}"
        )

        if not api_key:
            raise ValueError("OpenRouter API key is required")

        # Get category-specific prompts
        category_prompt = CATEGORY_PROMPTS.get(category, "")

        # Prepare base prompt
        base_prompt = PROMPT_TEMPLATE.format(
            category_prompts=category_prompt, output_language=output_language
        )

        # Prepare first chunk prompt with description request
        first_chunk_prompt = FIRST_CHUNK_TEMPLATE.format(base_prompt=base_prompt)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/GraniLuk/YouTubeToMarkdown",
            "X-OpenRouter-Title": "YT2MD",
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
                "temperature": 0.6,
            }

            response = None
            for attempt in range(max_retries):
                try:
                    response = requests.post(base_url, json=data, headers=headers)
                    response.raise_for_status()

                    result = response.json()

                    # Check for error in response body (some models return errors with HTTP 200)
                    if "error" in result:
                        error_obj = result["error"]
                        if isinstance(error_obj, dict):
                            error_msg = error_obj.get("message", str(error_obj))
                            error_code = error_obj.get("code", "unknown")
                            metadata = error_obj.get("metadata", {})
                            provider_name = metadata.get("provider_name", "unknown")
                            raw = metadata.get("raw", "")
                            logger.error(
                                f"OpenRouter error from provider '{provider_name}' "
                                f"(code: {error_code}): {error_msg}"
                            )
                            if raw:
                                logger.debug(f"OpenRouter raw provider error: {raw}")
                        else:
                            error_msg = str(error_obj)
                            logger.error(f"OpenRouter error: {error_msg}")
                        raise Exception(
                            f"OpenRouter error: {error_msg}"
                        )

                    # Validate response structure
                    if "choices" not in result or not result["choices"]:
                        logger.error(
                            f"OpenRouter unexpected response format: {str(result)[:500]}"
                        )
                        raise Exception(
                            f"OpenRouter returned unexpected response (no 'choices'). "
                            f"Response: {str(result)[:200]}"
                        )

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
                    status_code = response.status_code if response is not None else None
                    if (
                        status_code in (429, 503)
                        and attempt < max_retries - 1
                    ):
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(
                            f"OpenRouter API error {status_code} (attempt {attempt + 1}/{max_retries}), "
                            f"retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        response_text = (
                            response.text
                            if response is not None
                            else "No response text"
                        )
                        raise Exception(
                            f"OpenRouter HTTP {status_code}: {str(e)}, Response: {response_text}"
                        ) from e

                except Exception:
                    raise
            else:
                raise Exception("OpenRouter: Failed to get response after multiple retries")

        return "\n\n".join(final_output), description


class LLMFactory:
    """Factory class to create LLM strategies based on provider name."""

    @staticmethod
    def get_strategy(provider: str) -> LLMStrategy:
        """
        Get the appropriate LLM strategy based on provider name.

        Args:
            provider: The name of the LLM provider ("gemini", "perplexity", "ollama", "openrouter")

        Returns:
            LLMStrategy: The corresponding strategy implementation
        """
        strategies = {
            "gemini": GeminiStrategy(),
            "perplexity": PerplexityStrategy(),
            "ollama": OllamaStrategy(),
            "openrouter": OpenRouterStrategy(),
        }

        strategy = strategies.get(provider.lower())
        if not strategy:
            raise ValueError(f"Unknown LLM provider: {provider}")

        return strategy
