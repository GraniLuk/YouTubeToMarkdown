import os

from yt2md.llm_strategies import LLMFactory


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
                    print(
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
    model_name: str = "gemma3:4b",
    host: str = "http://localhost",
    port: int = 11434,
    output_language: str = "English",
    category: str = "IT",
) -> tuple[str, str]:
    """
    Analyze transcript using local Ollama instance.

    Args:
        transcript (str): Text transcript to analyze
        model_name (str): Ollama model name to use
        host (str): Ollama host address
        port (int): Ollama port
        output_language (str): Desired output language
        category (str): Category of the content (default: 'IT')

    Returns:
        tuple[str, str]: Refined and analyzed text, description
    """
    try:
        ollama_strategy = LLMFactory.get_strategy("ollama")
        return ollama_strategy.analyze_transcript(
            transcript=transcript,
            model_name=model_name,
            host=host,
            port=port,
            output_language=output_language,
            category=category,
        )
    except Exception as e:
        raise Exception(f"Ollama processing error: {str(e)}")


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
