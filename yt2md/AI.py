import os

from yt2md.config import get_llm_model_config, get_llm_strategy_for_transcript
from yt2md.llm_strategies import LLMFactory
from yt2md.logger import get_logger

logger = get_logger("AI")


def analyze_transcript_with_perplexity(
    transcript: str,
    api_key: str,
    perplexity_model_name: str,
    output_language: str,
    category: str,
    max_retries: int = 3,
    retry_delay: int = 2,
) -> tuple[str, str]:
    """
    Analyze transcript using Perplexity API.

    Args:
        transcript (str): The transcript text to analyze.
        api_key (str): Perplexity API key.
        perplexity_model_name (str): Perplexity model name to use.
        output_language (str): Desired output language.
        category (str): Category of the content.
        max_retries (int): Maximum number of retry attempts.
        retry_delay (int): Delay between retries in seconds.

    Returns:
        tuple[str, str]: Generated text and description from Perplexity API.
    """
    # Use the strategy pattern implementation
    strategy = LLMFactory.get_strategy("perplexity")

    refined_text, description = strategy.analyze_transcript(
        transcript=transcript,
        api_key=api_key,
        model_name=perplexity_model_name,
        output_language=output_language,
        category=category,
        max_retries=max_retries,
        retry_delay=retry_delay,
    )

    return refined_text, description


def analyze_transcript_with_gemini(
    transcript: str,
    api_key: str,
    gemini_model_name: str,
    output_language: str = "English",
    category: str = "IT",
) -> tuple[str, str]:
    """
    Analyze transcript using Gemini API and return refined text.

    Args:
        transcript (str): Text transcript to analyze
        api_key (str): Gemini API key
        gemini_model_name (str): Gemini model name to use.
        output_language (str): Desired output language
        category (str): Category of the content (default: 'IT')

    Returns:
        tuple[str, str]: Refined and analyzed text, description
    """
    # Use the strategy pattern implementation
    strategy = LLMFactory.get_strategy("gemini")
    refined_text, description = strategy.analyze_transcript(
        transcript=transcript,
        api_key=api_key,
        model_name=gemini_model_name,
        output_language=output_language,
        category=category,
    )
    return refined_text, description


def analyze_transcript_with_ollama(
    transcript: str,
    model_name: str,
    host: str,
    output_language: str = "English",
    category: str = "IT",
) -> tuple[str, str]:
    """
    Analyze transcript with Ollama.

    Args:
        transcript: The transcript text to analyze
        model_name: Name of the Ollama model to use
        host: Base URL for Ollama (e.g., "http://localhost:11434"), for backward compatibility
        output_language: Language for the output
        category: Content category

    Returns:
        tuple[str, str]: Refined text and description
    """
    try:
        ollama_strategy = LLMFactory.get_strategy("ollama")

        # Use configuration if model_name or host is not provided
        if not model_name or not host:
            # Get model config for this category
            ollama_config = get_llm_model_config("ollama", category)
            if not model_name:
                model_name = ollama_config.get(
                    "model_name", os.getenv("OLLAMA_MODEL", "gemma3:4b")
                )
            if not host:
                host = ollama_config.get(
                    "base_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
                )

        # Pass parameters to strategy
        return ollama_strategy.analyze_transcript(
            transcript=transcript,
            model_name=model_name,
            base_url=host,  # Pass host as base_url
            output_language=output_language,
            category=category,
        )
    except Exception as e:
        raise Exception(f"Ollama processing error: {str(e)}")


def analyze_transcript_by_length(
    transcript: str,
    ollama_model: str,
    ollama_base_url: str,
    output_language: str = "English",
    category: str = "IT",
    force_ollama: bool = False,
    force_cloud: bool = False,
) -> dict[str, dict[str, str]]:
    """
    Analyze transcript using different strategies based on transcript length and category.
    Cloud model names are fetched from configuration (channels.yaml).

    Strategy:
    - Determines primary and fallback models based on transcript length and content category
    - Model selection can be overridden using force_ollama or force_cloud
    - Configuration is loaded from channels.yaml with category-specific overrides
    - Supports provider+model configuration for flexible fallback (e.g., Gemini to different Gemini model)

    Args:
        transcript: Text transcript to analyze
        ollama_model: Name of the Ollama model to use (overrides config)
        ollama_base_url: Base URL for Ollama API (overrides config)
        output_language: Desired output language
        category: Category of the content (used for strategy selection)
        force_ollama: Whether to force using Ollama regardless of configuration
        force_cloud: Whether to force using cloud services only (overrides force_ollama)

    Returns:
        dict: Dictionary containing results from different LLMs with keys:              'cloud': {'text': refined_text, 'description': description, 'model_name': str, 'provider': str} if used
              'ollama': {'text': refined_text, 'description': description, 'model_name': str} if used
    """
    results = {}
    primary_model_failed = False

    # Get strategy configuration
    strategy_config = get_llm_strategy_for_transcript(transcript, category)
    primary = strategy_config.get("primary")
    fallback = strategy_config.get("fallback")

    # Helper function to resolve model name from config
    def get_model_name(provider, model_type, category):
        """Resolve actual model name from provider and model_type."""
        config = get_llm_model_config(provider, category)
        if provider == "gemini":
            if model_type == "primary":
                return config.get("primary_model", "gemini-2.5-flash-preview-09-2025")
            else:  # fallback
                return config.get("fallback_model", "gemini-1.5-flash-8b")
        elif provider == "ollama":
            return config.get("model_name", "ministral-3")
        return None

    # Ollama configuration
    ollama_config_from_file = get_llm_model_config("ollama", category)
    effective_ollama_model = ollama_model or (
        ollama_config_from_file.get("model_name")
        if ollama_config_from_file
        else "default_ollama_model"
    )
    effective_ollama_base_url = ollama_base_url or (
        ollama_config_from_file.get("base_url")
        if ollama_config_from_file
        else "http://localhost:11434"
    )
    use_ollama = bool(effective_ollama_model and effective_ollama_base_url)

    # Handle force flags - force_cloud takes precedence over force_ollama
    if force_cloud:
        logger.info("Forcing cloud-only processing.")
        # Primary will be determined by strategy_config, ollama will be skipped
    elif force_ollama:
        logger.info("Forcing Ollama processing.")
        primary = {"provider": "ollama", "model": effective_ollama_model}

    processed_cloud = False

    # Process with primary model
    if primary and primary["provider"] == "gemini" and not force_ollama:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        model_type = primary.get("model_type", "primary")
        model_name = get_model_name("gemini", model_type, category)

        if gemini_api_key and model_name:
            logger.info(
                f"Attempting to use Gemini model: {model_name} for category: {category} (primary)"
            )
            try:
                refined_text, description = analyze_transcript_with_gemini(
                    transcript=transcript,
                    api_key=gemini_api_key,
                    gemini_model_name=model_name,
                    output_language=output_language,
                    category=category,
                )
                results["cloud"] = {
                    "text": refined_text,
                    "description": description,
                    "model_name": model_name,
                    "provider": "gemini",
                }
                processed_cloud = True
                logger.debug(f"Successfully processed with Gemini: {model_name}")
            except Exception as e:
                logger.error(f"Error during Gemini processing with {model_name}: {e}")
                primary_model_failed = True
        else:
            logger.warning(
                "Gemini API key or model name not configured/found. Skipping Gemini."
            )
            primary_model_failed = True

    elif primary and primary["provider"] == "ollama" and not force_cloud:
        model_name = effective_ollama_model
        logger.info(f"Attempting to use Ollama model: {model_name} (primary)")
        try:
            if not model_name or not effective_ollama_base_url:
                raise ValueError(
                    "Ollama model name is missing. Please provide a valid model name."
                )
            ollama_refined_text, ollama_description = analyze_transcript_with_ollama(
                transcript=transcript,
                model_name=model_name,
                host=effective_ollama_base_url,
                output_language=output_language,
                category=category,
            )
            results["ollama"] = {
                "text": ollama_refined_text,
                "description": ollama_description,
                "model_name": model_name,
            }
            logger.debug(f"Successfully processed with Ollama: {model_name}")
        except Exception as e:
            logger.error(f"Error during Ollama processing with {model_name}: {e}")
            primary_model_failed = True

    # Process with fallback model if primary failed
    if primary_model_failed and fallback:
        if fallback["provider"] == "gemini" and not force_ollama:
            gemini_api_key = os.getenv("GEMINI_API_KEY")
            model_type = fallback.get("model_type", "fallback")
            model_name = get_model_name("gemini", model_type, category)

            if gemini_api_key and model_name:
                logger.info(
                    f"Attempting to use Gemini model: {model_name} for category: {category} (fallback)"
                )
                try:
                    refined_text, description = analyze_transcript_with_gemini(
                        transcript=transcript,
                        api_key=gemini_api_key,
                        gemini_model_name=model_name,
                        output_language=output_language,
                        category=category,
                    )
                    results["cloud"] = {
                        "text": refined_text,
                        "description": description,
                        "model_name": model_name,
                        "provider": "gemini",
                    }
                    processed_cloud = True
                    logger.debug(
                        f"Successfully processed with Gemini fallback: {model_name}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error during Gemini fallback processing with {model_name}: {e}"
                    )
            else:
                logger.warning(
                    "Gemini API key or model name not configured/found for fallback."
                )

        elif fallback["provider"] == "ollama" and not force_cloud and use_ollama:
            model_name = effective_ollama_model
            logger.info(f"Attempting to use Ollama model: {model_name} (fallback)")
            try:
                if not model_name or not effective_ollama_base_url:
                    raise ValueError(
                        "Ollama model name is missing. Please provide a valid model name."
                    )
                ollama_refined_text, ollama_description = (
                    analyze_transcript_with_ollama(
                        transcript=transcript,
                        model_name=model_name,
                        host=effective_ollama_base_url,
                        output_language=output_language,
                        category=category,
                    )
                )
                results["ollama"] = {
                    "text": ollama_refined_text,
                    "description": ollama_description,
                    "model_name": model_name,
                }
                logger.debug(
                    f"Successfully processed with Ollama fallback: {model_name}"
                )
            except Exception as e:
                logger.error(
                    f"Error during Ollama fallback processing with {model_name}: {e}"
                )

    if not results:
        logger.error(
            "No LLM processing was successful or configured for the given parameters."
        )

    return results


if __name__ == "__main__":
    # Example usage
    transcript_text_from_file = "C:\\Users\\5028lukgr\\Downloads\\Geeks Club-20250319_080718-Meeting Recording-en-US.txt"
    with open(transcript_text_from_file, "r") as file:
        transcript = file.read()
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")

    if not gemini_api_key or not perplexity_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable not set.  An API key is required."
        )

    newTranscript = analyze_transcript_with_gemini(
        transcript=transcript,
        api_key=gemini_api_key,
        gemini_model_name="gemini-2.5-pro-exp-03-25",
        output_language="English",
        category="IT",
    )
    print(newTranscript[0])
    print(newTranscript[1])
    # Save the refined transcript to a file
    with open("refined_transcript.txt", "w") as file:
        file.write(newTranscript[0])
