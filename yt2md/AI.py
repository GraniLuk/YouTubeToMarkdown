import google.generativeai as genai

def analyze_transcript_with_gemini(
    transcript: str,
    api_key: str,
    model_name: str = "gemini-1.5-pro",
    output_language: str = "English",
    chunk_size: int = 3000,
    category: str = "IT",
) -> tuple[str, str]:
    """
    Analyze transcript using Gemini API and return refined text.

    Args:
        transcript (str): Text transcript to analyze
        api_key (str): Gemini API key
        model_name (str): Gemini model name to use
        output_language (str): Desired output language
        chunk_size (int): Maximum chunk size for processing
        category (str): Category of the content (default: 'IT')

    Returns:
        str: Refined and analyzed text
    """
    try:
        # Configure Gemini
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)

        # Split transcript into chunks if it's too long
        words = transcript.split()
        chunks = [
            " ".join(words[i : i + chunk_size])
            for i in range(0, len(words), chunk_size)
        ]

        # Process each chunk
        final_output = []
        previous_response = ""

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

        for i, chunk in enumerate(chunks):
            # Prepare prompt with context if needed
            if previous_response:
                context_prompt = (
                    "The following text is a continuation... "
                    f"Previous response:\n{previous_response}\n\nNew text to process(Do Not Repeat the Previous response:):\n"
                )
            else:
                context_prompt = ""

            # Create full prompt
            formatted_prompt = PROMPT_TEMPLATE.replace("[Language]", output_language)
            full_prompt = f"{context_prompt}{formatted_prompt}\n\n{chunk}"

            # Generate response
            response = model.generate_content(full_prompt)
            previous_response = response.text
            final_output.append(response.text)

        metadata_prompt = f"""Based on the following content, provide:
1. A concise one-sentence description of the content.

Content:
{previous_response}"""

        metadata_response = model.generate_content(metadata_prompt)
        metadata_text = metadata_response.text

        # Parse the response to extract description and
        try:
            # Split the response into lines and clean them up
            lines = [line.strip() for line in metadata_text.split('\n') if line.strip()]
            description = lines[0].replace('1.', '').strip()
        except Exception as e:
            # Fallback values if parsing fails
            description = "No description available"

        return "\n\n".join(final_output), description

    except Exception as e:
        raise Exception(f"Gemini processing error: {str(e)}")