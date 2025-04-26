import os

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
    model_name: str = "gemini-1.5-pro",
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
                    return perplexity_strategy.analyze_transcript(
                        transcript=transcript,
                        api_key=perplexity_api_key,
                        model_name="sonar-pro",
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
    cloud_model_name: str = "gemini-1.5-pro",
    output_language: str = "English",
    category: str = "IT",
    force_ollama: bool = False,
    force_cloud: bool = False,
) -> dict:
    """
    Analyze transcript using different strategies based on transcript length.

    Strategy:
    - If force_cloud is True: Use only cloud (Gemini with Perplexity fallback)
    - If force_ollama is True: Use only Ollama
    - If transcript length < 1000: Use Ollama only
    - If transcript length between 1000-3000: Use both Ollama and cloud (Gemini/Perplexity)
    - If transcript length > 3000: Use only cloud (Gemini with Perplexity fallback)

    Args:
        transcript: Text transcript to analyze
        api_key: Gemini API key
        perplexity_api_key: Perplexity API key for fallback (optional)
        ollama_model: Name of the Ollama model to use
        ollama_base_url: Base URL for Ollama API
        cloud_model_name: Gemini model name to use
        output_language: Desired output language
        category: Category of the content
        force_ollama: Whether to force using Ollama regardless of transcript length
        force_cloud: Whether to force using cloud services only

    Returns:
        dict: Dictionary containing results from different LLMs with keys:
              'cloud': (refined_text, description) from cloud provider if used
              'ollama': (refined_text, description) from Ollama if used
    """
    results = {}
    transcript_length = len(transcript)

    # Handle force flags - force_cloud takes precedence over force_ollama
    if force_cloud:
        use_cloud = True
        use_ollama = False
    elif force_ollama:
        use_cloud = False
        use_ollama = True
    else:
        # Determine which strategies to use based on transcript length
        use_ollama = transcript_length < 3000
        use_cloud = transcript_length > 1000 or not use_ollama

    # Log the strategy being used
    if use_ollama and use_cloud:
        logger.info("Using both cloud and local LLM processing")
    elif use_ollama:
        logger.info("Using only local LLM (Ollama) processing")
    else:
        logger.info("Using only cloud LLM processing")

    # Process with cloud LLM if needed
    if use_cloud:
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
        except Exception as e:
            logger.error(f"Error with cloud LLM processing: {str(e)}")

    # Process with Ollama if needed
    if use_ollama:
        try:
            ollama_result = analyze_transcript_with_ollama(
                transcript=transcript,
                model_name=ollama_model,
                host=ollama_base_url,
                output_language=output_language,
                category=category,
            )
            results["ollama"] = ollama_result
        except Exception as e:
            logger.error(f"Error with Ollama processing: {str(e)}")
            # If Ollama was the only strategy and it failed, try cloud as fallback
            if not use_cloud and "cloud" not in results:
                logger.info("Falling back to cloud LLM processing...")
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
