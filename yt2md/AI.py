import os

from yt2md.config import get_llm_model_config, get_llm_strategy_for_transcript
from yt2md.llm_strategies import LLMFactory
from yt2md.logger import get_logger

logger = get_logger("AI")


def analyze_transcript_with_perplexity(
    prompt: str,
    api_key: str,
    model_name: str = "sonar-pro",
    max_retries: int = 3,
    retry_delay: int = 2,
) -> str:
    """
    Fallback function to analyze transcript using Perplexity API when Gemini fails.

    Args:
        prompt (str): The prompt to send to Perplexity API
        api_key (str): Perplexity API key
        model_name (str): Perplexity model name to use
        max_retries (int): Maximum number of retry attempts
        retry_delay (int): Delay between retries in seconds

    Returns:
        str: Generated text from Perplexity API
    """
    # Use the strategy pattern implementation
    strategy = LLMFactory.get_strategy("perplexity")

    # Extract transcript from prompt - simplified approach, might need adjustment
    # This assumes the prompt ends with "Text:" followed by the transcript
    text_parts = prompt.split("Text:\n\n")
    if len(text_parts) > 1:
        transcript = text_parts[-1]
    else:
        transcript = prompt

    refined_text, _ = strategy.analyze_transcript(
        transcript=transcript,
        api_key=api_key,
        model_name=model_name,
        max_retries=max_retries,
        retry_delay=retry_delay,
    )

    return refined_text


def analyze_transcript_with_gemini(
    transcript: str,
    api_key: str,
    perplexity_api_key: str = None,
    model_name: str = "gemini-2.5-pro-exp-03-25",
    output_language: str = "English",
    category: str = "IT",
) -> tuple[str, str]:
    """
    Analyze transcript using Gemini API and return refined text.
    Falls back to Perplexity API if Gemini returns a 429 error.

    Args:
        transcript (str): Text transcript to analyze
        api_key (str): Gemini API key
        perplexity_api_key (str): Perplexity API key for fallback
        model_name (str): Gemini model name to use
        output_language (str): Desired output language
        category (str): Category of the content (default: 'IT')

    Returns:
        tuple[str, str]: Refined and analyzed text, description
    """
    try:
        # Use the strategy pattern implementation
        gemini_strategy = LLMFactory.get_strategy("gemini")

        # Get model config for this category
        gemini_config = get_llm_model_config("gemini", category)
        if gemini_config and "model_name" in gemini_config:
            model_name = gemini_config["model_name"]

        try:
            return gemini_strategy.analyze_transcript(
                transcript=transcript,
                api_key=api_key,
                model_name=model_name,
                output_language=output_language,
                category=category,
            )
        except Exception as e:
            error_message = str(e).lower()
            if "429" in error_message or "too many requests" in error_message:
                # Fallback to Perplexity API if Gemini returns a 429 error and a key is provided
                if perplexity_api_key:
                    logger.warning(
                        "Gemini API rate limit hit, falling back to Perplexity API..."
                    )
                    perplexity_strategy = LLMFactory.get_strategy("perplexity")

                    # Get model config for this category
                    perplexity_config = get_llm_model_config("perplexity", category)
                    perplexity_model = perplexity_config.get("model_name", "sonar-pro")

                    return perplexity_strategy.analyze_transcript(
                        transcript=transcript,
                        api_key=perplexity_api_key,
                        model_name=perplexity_model,
                        output_language=output_language,
                        category=category,
                    )
                else:
                    raise Exception(
                        "Gemini API rate limit hit and no Perplexity API key provided for fallback"
                    )
            else:
                # Re-raise other exceptions
                raise Exception(f"Gemini API error: {str(e)}")

    except Exception as e:
        raise Exception(f"AI processing error: {str(e)}")


def analyze_transcript_with_ollama(
    transcript: str,
    model_name: str = None,
    host: str = None,
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
    api_key: str,
    perplexity_api_key: str = None,
    ollama_model: str = None,
    ollama_base_url: str = None,
    cloud_model_name: str = "gemini-2.5-pro-exp-03-25",
    output_language: str = "English",
    category: str = "IT",
    force_ollama: bool = False,
    force_cloud: bool = False,
) -> dict:
    """
    Analyze transcript using different strategies based on transcript length and category.

    Strategy:
    - Determines primary and fallback models based on transcript length and content category
    - Model selection can be overridden using force_ollama or force_cloud
    - Configuration is loaded from channels.yaml with category-specific overrides

    Args:
        transcript: Text transcript to analyze
        api_key: Gemini API key
        perplexity_api_key: Perplexity API key for fallback (optional)
        ollama_model: Name of the Ollama model to use (overrides config)
        ollama_base_url: Base URL for Ollama API (overrides config)
        cloud_model_name: Gemini model name to use (overrides config)
        output_language: Desired output language
        category: Category of the content (used for strategy selection)
        force_ollama: Whether to force using Ollama regardless of configuration
        force_cloud: Whether to force using cloud services only (overrides force_ollama)

    Returns:
        dict: Dictionary containing results from different LLMs with keys:
              'cloud': (refined_text, description) from cloud provider if used
              'ollama': (refined_text, description) from Ollama if used
    """
    results = {}

    # Handle force flags - force_cloud takes precedence over force_ollama
    if force_cloud:
        use_ollama = False
        logger.info("Forced cloud LLM processing")
    elif force_ollama:
        use_ollama = True
        logger.info("Forced local LLM (Ollama) processing")
    else:
        # Get recommended strategy based on transcript length and category
        strategy = get_llm_strategy_for_transcript(transcript, category)
        primary_model = strategy.get("primary", "gemini")
        fallback_model = strategy.get("fallback", "perplexity")

        # Determine which models to use
        use_ollama = primary_model == "ollama" or fallback_model == "ollama"

        # Determine the order of processing
        # Log the strategy being used
        logger.info(
            f"Using strategy for {category} category: primary={primary_model}, fallback={fallback_model}"
        )

    # Process with primary model first, then fallback if needed
    processed = False

    # Process with gemini if it's the primary model or we're forced to use cloud
    if (force_cloud or primary_model == "gemini") and not processed:
        try:
            logger.info("Processing with Gemini")
            cloud_result = analyze_transcript_with_gemini(
                transcript=transcript,
                api_key=api_key,
                perplexity_api_key=perplexity_api_key,  # Provide for potential internal fallback
                model_name=cloud_model_name,
                output_language=output_language,
                category=category,
            )
            results["cloud"] = cloud_result
            processed = True
        except Exception as e:
            logger.error(f"Error with Gemini processing: {str(e)}")

    # Process with perplexity if it's the primary model or gemini failed
    if (
        primary_model == "perplexity" or (force_cloud and not processed)
    ) and perplexity_api_key:
        try:
            logger.info("Processing with Perplexity")
            perplexity_strategy = LLMFactory.get_strategy("perplexity")
            # Get model config for this category
            perplexity_config = get_llm_model_config("perplexity", category)
            perplexity_model = perplexity_config.get("model_name", "sonar-pro")

            perplexity_result = perplexity_strategy.analyze_transcript(
                transcript=transcript,
                api_key=perplexity_api_key,
                model_name=perplexity_model,
                output_language=output_language,
                category=category,
            )
            results["perplexity"] = perplexity_result
            processed = True
        except Exception as e:
            logger.error(f"Error with Perplexity processing: {str(e)}")

    # Process with Ollama if it's the primary model or no cloud results yet and we can use ollama
    if (primary_model == "ollama" or force_ollama or not processed) and use_ollama:
        try:
            logger.info("Processing with Ollama")
            ollama_result = analyze_transcript_with_ollama(
                transcript=transcript,
                model_name=ollama_model,
                host=ollama_base_url,
                output_language=output_language,
                category=category,
            )
            results["ollama"] = ollama_result
            processed = True
        except Exception as e:
            logger.error(f"Error with Ollama processing: {str(e)}")

    # If we still haven't processed anything, try any available fallback
    if not processed:
        if not force_ollama and api_key:
            logger.info("All primary methods failed. Trying Gemini as final fallback.")
            try:
                cloud_result = analyze_transcript_with_gemini(
                    transcript=transcript,
                    api_key=api_key,
                    perplexity_api_key=perplexity_api_key,
                    model_name=cloud_model_name,
                    output_language=output_language,
                    category=category,
                )
                results["cloud"] = cloud_result
            except Exception as cloud_error:
                logger.error(f"Cloud fallback also failed: {str(cloud_error)}")
        elif not force_cloud:
            logger.info("All primary methods failed. Trying Ollama as final fallback.")
            try:
                ollama_result = analyze_transcript_with_ollama(
                    transcript=transcript,
                    model_name=ollama_model,
                    host=ollama_base_url,
                    output_language=output_language,
                    category=category,
                )
                results["ollama"] = ollama_result
            except Exception as ollama_error:
                logger.error(f"Ollama fallback also failed: {str(ollama_error)}")

    return results


if __name__ == "__main__":
    # Example usage
    transcript_text_from_file = "C:\\Users\\5028lukgr\\Downloads\\Geeks Club-20250319_080718-Meeting Recording-en-US.txt"
    with open(transcript_text_from_file, "r") as file:
        transcript = file.read()
    api_key = os.getenv("GEMINI_API_KEY")
    perplexity_key = os.getenv("PERPLEXITY_API_KEY")

    newTranscript = analyze_transcript_with_gemini(
        transcript=transcript,
        api_key=api_key,
        perplexity_api_key=perplexity_key,
        model_name="gemini-2.5-pro-exp-03-25",
        output_language="English",
        category="IT",
    )
    print(newTranscript[0])
    print(newTranscript[1])
    # Save the refined transcript to a file
    with open("refined_transcript.txt", "w") as file:
        file.write(newTranscript[0])
