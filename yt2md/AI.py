import os
import time

import google.generativeai as genai
import requests


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
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    data = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 4000,
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()

            result = response.json()
            return result["choices"][0]["message"]["content"]

        except requests.exceptions.HTTPError as e:
            if response.status_code == 429 and attempt < max_retries - 1:
                # If rate limited, wait and retry
                wait_time = retry_delay * (attempt + 1)
                print(f"Perplexity API rate limit hit, retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                # Re-raise the exception if it's not a rate limit or we've exhausted retries
                raise Exception(
                    f"Perplexity API error: {str(e)}, Response: {response.text}"
                )

        except Exception as e:
            raise Exception(f"Perplexity API error: {str(e)}")


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
        # Configure Gemini
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)

        # Split transcript into chunks if it's too long
        chunk_size = 6000  # Adjust chunk size as needed
        words = transcript.split()
        chunks = [
            " ".join(words[i : i + chunk_size])
            for i in range(0, len(words), chunk_size)
        ]

        # Process each chunk
        final_output = []
        previous_response = ""
        description = "No description available"

        # Define category-specific bullet points
        category_prompts = {
            "IT": "- Adding code examples in C# when it's possible\n - Write diagram in mermaid syntax when it can help understand discussed subject",
            "Crypto": "- Adding TradingView chart links when price movements or technical analysis is discussed\n- Highlighting key price levels and market indicators mentioned\n- Including links to relevant blockchain explorers when specific transactions or contracts are discussed",
        }

        PROMPT_TEMPLATE = f"""
Turn the following unorganized text into a well-structured, readable format while retaining EVERY detail, context, and nuance of the original content.
Refine the text to improve clarity, grammar, and coherence WITHOUT cutting, summarizing, or omitting any information.
The goal is to make the content easier to read and process by:

- Organizing the content into logical sections with appropriate subheadings.
- Using bullet points or numbered lists where applicable to present facts, stats, or comparisons.
- Highlighting key terms, names, or headings with bold text for emphasis.
- Preserving the original tone, humor, and narrative style while ensuring readability.
- Adding clear separators or headings for topic shifts to improve navigation.
{category_prompts.get(category, "")}

Ensure the text remains informative, capturing the original intent, tone,
and details while presenting the information in a format optimized for analysis by both humans and AI.
REMEMBER that Details are important, DO NOT overlook Any details, even small ones.
All output must be generated entirely in [Language]. Do not use any other language at any point in the response.
Text:
"""

        FIRST_CHUNK_TEMPLATE = f'First, provide a one-sentence description of the content (start with "DESCRIPTION:").\nThen, {PROMPT_TEMPLATE}'

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
            if i == 0:
                template = FIRST_CHUNK_TEMPLATE
            else:
                template = PROMPT_TEMPLATE

            # Create full prompt
            formatted_prompt = template.replace("[Language]", output_language)
            full_prompt = f"{context_prompt}{formatted_prompt}\n\n{chunk}"

            # Generate response with fallback to Perplexity API on 429 error
            try:
                response = model.generate_content(full_prompt)
                text = response.text
            except Exception as e:
                error_message = str(e).lower()
                if "429" in error_message or "too many requests" in error_message:
                    # Fallback to Perplexity API if Gemini returns a 429 error and a key is provided
                    if perplexity_api_key:
                        print(
                            "Gemini API rate limit hit, falling back to Perplexity API..."
                        )
                        text = analyze_transcript_with_perplexity(
                            prompt=full_prompt,
                            api_key=perplexity_api_key,
                            model_name="sonar-pro",
                        )
                    else:
                        raise Exception(
                            "Gemini API rate limit hit and no Perplexity API key provided for fallback"
                        )
                else:
                    # Re-raise other exceptions
                    raise Exception(f"Gemini API error: {str(e)}")

            # Extract description from first chunk
            if i == 0:
                lines = text.split("\n")
                if lines[0].startswith("DESCRIPTION:"):
                    description = lines[0].replace("DESCRIPTION:", "").strip()
                    text = "\n".join(lines[1:])
                if lines[0].startswith("OPIS:"):
                    description = lines[0].replace("OPIS:", "").strip()
                    text = "\n".join(lines[1:])

            previous_response = text
            final_output.append(text)

        return "\n\n".join(final_output), description

    except Exception as e:
        raise Exception(f"AI processing error: {str(e)}")


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
        model_name="gemini-2.0-pro-exp-02-05",
        output_language="English",
        category="IT",
    )
    print(newTranscript[0])
    print(newTranscript[1])
    # Save the refined transcript to a file
    with open("refined_transcript.txt", "w") as file:
        file.write(newTranscript[0])
