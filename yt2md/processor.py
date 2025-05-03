"""Video processing functionality for the YouTube to Markdown converter."""

import os
import time

import colorama

from yt2md.AI import analyze_transcript_by_length
from yt2md.file_operations import save_to_markdown
from yt2md.logger import colored_text, get_logger
from yt2md.youtube import get_youtube_transcript

# Get logger for this module
logger = get_logger("processor")


def process_video(
    video_url,
    video_title,
    published_date,
    author_name,
    language_code,
    output_language,
    category,
    use_ollama=False,
    use_cloud=False,
    skip_verification=False,
    ollama_model=None,
    ollama_base_url=None,
):
    """
    Process a single video: get transcript, analyze with appropriate LLM based on transcript length, and save to markdown.

    Args:
        video_url: YouTube video URL
        video_title: Title of the video
        published_date: Date when the video was published
        author_name: Channel/author name
        language_code: Language code for the transcript
        output_language: Target language for the output
        category: Video category
        use_ollama: Whether to force using Ollama regardless of transcript length
        use_cloud: Whether to force using cloud services only for processing
        skip_verification: If True, skip checking if video was already processed and don't update index
        ollama_model: Ollama model to use (if None, use environment variable)
        ollama_base_url: Ollama base URL (if None, use environment variable)

    Returns:
        list: Paths to the saved file(s) or None if processing failed
    """
    # Use environment variables if parameters are not provided
    if ollama_model is None:
        ollama_model = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    if ollama_base_url is None:
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    try:
        logger.info(
            f"Processing video: {video_title} by {author_name} with URL: {video_url}"
        )
        saved_files = []

        # Get transcript
        transcript = get_youtube_transcript(video_url, language_code=language_code)
        if transcript is None:
            # The error has already been logged in get_youtube_transcript
            logger.error(
                f"Error processing video {video_title}: Transcript extraction failed"
            )
            return None

        transcript_length = len(transcript.split())
        logger.info(
            colored_text(
                f"Transcript length: {transcript_length} words", colorama.Fore.CYAN
            )
        )

        # Get API keys from environment
        api_key = os.getenv("GEMINI_API_KEY")
        perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")

        # Measure execution time for transcript analysis
        start_time = time.time()
        results = analyze_transcript_by_length(
            transcript=transcript,
            api_key=api_key,
            perplexity_api_key=perplexity_api_key,
            ollama_model=ollama_model,
            ollama_base_url=ollama_base_url,
            cloud_model_name="gemini-2.5-pro-exp-03-25",
            output_language=output_language,
            category=category,
            force_ollama=use_ollama,
            force_cloud=use_cloud,
        )
        execution_time = time.time() - start_time
        minutes = int(execution_time // 60)
        seconds = execution_time % 60
        logger.info(
            colored_text(
                f"Transcript analysis completed in {minutes} min {seconds:.2f} sec",
                colorama.Fore.CYAN,
            )
        )

        # Save cloud LLM result if available
        if "cloud" in results:
            refined_text, description = results["cloud"]

            # Extract model name for the suffix
            if skip_verification:
                model_suffix = "gemini-2.5-pro-exp-03-25".split("-")[
                    0
                ]  # Get first part of the model name (e.g., "gemini")
            else:
                model_suffix = None  # Default to None if not skipping verification

            # Save cloud LLM result to markdown file
            saved_file_path = save_to_markdown(
                video_title,
                video_url,
                refined_text,
                author_name,
                published_date,
                description,
                category,
                suffix=model_suffix,
                skip_verification=skip_verification,
            )

            if saved_file_path:
                logger.info(f"Saved cloud LLM result to: {saved_file_path}")
                saved_files.append(saved_file_path)

        # Save Ollama result if available
        if "ollama" in results:
            ollama_refined_text, ollama_description = results["ollama"]

            # Use ollama model name as suffix, clean it up if needed
            ollama_suffix = ollama_model.split(":")[0]  # Remove version tag if present

            # Save Ollama result to markdown with suffix
            ollama_file_path = save_to_markdown(
                video_title,
                video_url,
                ollama_refined_text,
                author_name,
                published_date,
                ollama_description,
                category,
                suffix=ollama_suffix,
                skip_verification=skip_verification,
            )

            if ollama_file_path:
                logger.info(f"Saved Ollama result to: {ollama_file_path}")
                saved_files.append(ollama_file_path)

        return saved_files

    except Exception as e:
        # Log error message without stack trace
        error_msg = str(e).split("!")[0] if "!" in str(e) else str(e)
        logger.error(f"Error processing video {video_title}: {error_msg}")
        return None
