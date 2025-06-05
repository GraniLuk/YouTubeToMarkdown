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
    Falls back to Perplexity API if Gemini returns an error (handled by strategy or this func).

    Args:
        transcript (str): Text transcript to analyze
        api_key (str): Gemini API key
        gemini_model_name (str): Gemini model name to use.
        output_language (str): Desired output language
        category (str): Category of the content (default: 'IT')

    Returns:
        tuple[str, str]: Refined and analyzed text, description
    """

    perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
    try:
        # Use the strategy pattern implementation
        strategy = LLMFactory.get_strategy("gemini")
        refined_text, description = strategy.analyze_transcript(
            transcript=transcript,
            api_key=api_key,
            model_name=gemini_model_name,
            output_language=output_language,
            category=category,
            # perplexity_api_key might be used by the strategy if it has internal fallback
        )
        return refined_text, description
    except Exception as e:
        logger.error(f"Gemini API call failed: {e}")
        if "429" in str(e) and perplexity_api_key:
            logger.info(
                "Falling back to Perplexity API due to Gemini 429 error..."
            )  # Fetch perplexity model name from config for fallback
            perplexity_config = get_llm_model_config("perplexity", category)
            fallback_perplexity_model_name = (
                perplexity_config.get("model_name")
                if perplexity_config
                else "sonar-pro"
            )  # Default fallback model

            if not fallback_perplexity_model_name:
                logger.error(
                    "Perplexity model name not configured for fallback. Cannot proceed with fallback."
                )
                raise  # Re-raise the original exception if fallback model is not found

            return analyze_transcript_with_perplexity(
                transcript=transcript,
                api_key=perplexity_api_key,
                perplexity_model_name=fallback_perplexity_model_name,
                output_language=output_language,
                category=category,
            )
        raise  # Re-raise original exception if no Perplexity API key available


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
    primary_model_failed = False  # Track if primary model failed

    # Determine primary and fallback models from strategy config
    strategy_config = get_llm_strategy_for_transcript(
        transcript,
        category,  # Pass the transcript string directly
    )
    primary_model_type = strategy_config.get("primary")
    fallback_model_type = strategy_config.get("fallback")
    gemini_config = get_llm_model_config("gemini", category)
    gemini_model_name = gemini_config.get("model_name") if gemini_config else None
    perplexity_config = get_llm_model_config("perplexity", category)
    perplexity_model_name = (
        perplexity_config.get("model_name") if perplexity_config else None
    )

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
        primary_model_type = "ollama"  # Override strategy if forcing ollama

    processed_cloud = False

    # Process with Gemini
    if not force_ollama and (force_cloud or primary_model_type == "gemini"):
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key and gemini_model_name:
            logger.info(
                f"Attempting to use Gemini model: {gemini_model_name} for category: {category}"
            )
            try:
                refined_text, description = analyze_transcript_with_gemini(
                    transcript=transcript,
                    api_key=gemini_api_key,
                    gemini_model_name=gemini_model_name,
                    output_language=output_language,
                    category=category,
                )
                results["cloud"] = {
                    "text": refined_text,
                    "description": description,
                    "model_name": gemini_model_name,
                    "provider": "gemini",
                }
                processed_cloud = True
                logger.debug(f"Successfully processed with Gemini: {gemini_model_name}")
            except Exception as e:
                logger.error(
                    f"Error during Gemini processing with {gemini_model_name}: {e}"
                )                # Mark primary as failed if Gemini was the primary model
                if primary_model_type == "gemini":
                    primary_model_failed = True
        else:
            logger.warning(
                "Gemini API key or model name not configured/found. Skipping Gemini."
            )
            # Mark primary as failed if Gemini was the primary model but not configured
            if primary_model_type == "gemini":
                primary_model_failed = True

    # Process with Perplexity if not already processed by Gemini and conditions met
    if (
        not processed_cloud
        and not force_ollama
        and (
            force_cloud
            or primary_model_type == "perplexity"
            or (primary_model_failed and fallback_model_type == "perplexity")
        )
    ):
        perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
        if not perplexity_api_key:
            logger.warning(
                "Perplexity API key not configured. Skipping Perplexity processing."
            )
            return results
        if perplexity_api_key and perplexity_model_name:
            # Determine if this is a fallback attempt
            is_fallback = (
                primary_model_type != "perplexity"
                and fallback_model_type == "perplexity"
            )
            log_message = f"Attempting to use Perplexity model: {perplexity_model_name} for category: {category}"
            if is_fallback:
                log_message += " (fallback from failed primary model)"
            logger.info(log_message)
            try:
                refined_text, description = analyze_transcript_with_perplexity(
                    transcript=transcript,
                    api_key=perplexity_api_key,
                    perplexity_model_name=perplexity_model_name,
                    output_language=output_language,
                    category=category,
                )
                results["cloud"] = {
                    "text": refined_text,
                    "description": description,
                    "model_name": perplexity_model_name,
                    "provider": "perplexity",
                }
                processed_cloud = True
                logger.debug(
                    f"Successfully processed with Perplexity: {perplexity_model_name}"
                )
            except Exception as e:
                logger.error(
                    f"Error during Perplexity processing with {perplexity_model_name}: {e}"
                )                # Mark primary as failed if Perplexity was the primary model
                if primary_model_type == "perplexity":
                    primary_model_failed = True
        else:
            logger.warning(
                "Perplexity API key or model name not configured/found. Skipping Perplexity."
            )
            # Mark primary as failed if Perplexity was the primary model but not configured
            if primary_model_type == "perplexity":
                primary_model_failed = True

    # Process with Ollama if forced, or primary, or fallback when primary failed
    if use_ollama and (
        force_ollama 
        or primary_model_type == "ollama" 
        or (primary_model_failed and fallback_model_type == "ollama")
        or (not processed_cloud and primary_model_type in ["gemini", "perplexity"] and fallback_model_type == "ollama")    ):
        # Determine if Ollama is running as a fallback
        is_ollama_fallback = (
            primary_model_failed and fallback_model_type == "ollama"
        ) or (
            not processed_cloud and primary_model_type in ["gemini", "perplexity"] and fallback_model_type == "ollama"
        )
        
        log_message = f"Attempting to use Ollama model: {effective_ollama_model}"
        if is_ollama_fallback:
            log_message += " (fallback from failed primary model)"
        logger.info(log_message)
        try:
            if not effective_ollama_model or not effective_ollama_base_url:
                raise ValueError(
                    "Ollama model name is missing. Please provide a valid model name."
                )
            ollama_refined_text, ollama_description = analyze_transcript_with_ollama(
                transcript=transcript,
                model_name=effective_ollama_model,
                host=effective_ollama_base_url,
                output_language=output_language,
                category=category,
            )
            results["ollama"] = {
                "text": ollama_refined_text,
                "description": ollama_description,
                "model_name": effective_ollama_model,
            }
            logger.debug(
                f"Successfully processed with Ollama: {effective_ollama_model}"
            )
        except Exception as e:
            logger.error(
                f"Error during Ollama processing with {effective_ollama_model}: {e}"
            )
            # Mark primary as failed if Ollama was the primary model
            if primary_model_type == "ollama":
                primary_model_failed = True
            
            if (
                "ollama" not in results and not processed_cloud
            ):  # if ollama was the only hope and failed
                logger.warning(
                    "All processing attempts failed (Ollama was last attempt)."
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
