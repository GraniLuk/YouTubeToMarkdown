import os
import time

import colorama

from yt2md.AI import analyze_transcript_by_length
from yt2md.file_operations import save_to_markdown
from yt2md.logger import colored_text, get_logger
from yt2md.youtube import get_youtube_transcript

# Get logger for this module
logger = get_logger("processor")


# Batch processing function for a list of videos, with progress logging
def process_videos(
    videos_to_process,
    use_ollama=False,
    use_cloud=False,
    skip_verification=False,
    ollama_model=None,
    ollama_base_url=None,
    disable_kindle_auto: bool = False,
):
    """
    Process a list of videos, logging progress count in the existing log about processing each video.
    Args:
        videos_to_process: list of tuples with video parameters
        use_ollama, use_cloud, skip_verification, ollama_model, ollama_base_url: see process_video
    """
    total = len(videos_to_process)
    start_time = time.time()
    all_results = []
    # Kindle auto-send counters (per-video immediate sending)
    kindle_sent = 0
    kindle_failed = 0

    # Lazy import flag so we only import kindle utilities if KINDLE_EMAIL is set
    kindle_enabled = bool(os.getenv("KINDLE_EMAIL")) and not disable_kindle_auto
    kindle_module = None

    for idx, (
        video_url,
        video_title,
        published_date,
        channel_name,
        language_code,
        output_language,
        category,
    ) in enumerate(videos_to_process, 1):
        logger.info(
            f"Processing video {idx}/{total}: {video_title} by {channel_name} with URL: {video_url}"
        )
        res = process_video(
            video_url,
            video_title,
            published_date,
            channel_name,
            language_code,
            output_language,
            category,
            use_ollama=use_ollama,
            use_cloud=use_cloud,
            skip_verification=skip_verification,
            ollama_model=ollama_model,
            ollama_base_url=ollama_base_url,
        )
        if res:
            all_results.extend(res)
            # Immediately attempt Kindle auto-send for any long notes from this video
            if kindle_enabled:
                try:
                    if kindle_module is None:
                        from yt2md.email import kindle as kindle_module  # type: ignore
                    sent, failed = kindle_module.auto_send_long_notes(res)
                    kindle_sent += sent
                    kindle_failed += failed
                except Exception as e:  # pragma: no cover
                    logger.error(f"Kindle immediate send error: {e}")
    execution_time = time.time() - start_time
    minutes = int(execution_time // 60)
    seconds = execution_time % 60
    logger.info(f"All videos processed in {minutes} min {seconds:.2f} sec")
    if kindle_enabled and (kindle_sent or kindle_failed):
        logger.info(
            f"Kindle immediate send summary: sent={kindle_sent} failed={kindle_failed}"
        )
    return all_results


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
    Cloud model names are determined by the configuration in channels.yaml.

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

        # Measure execution time for transcript analysis
        start_time = time.time()
        results = analyze_transcript_by_length(
            transcript=transcript,
            ollama_model=ollama_model,
            ollama_base_url=ollama_base_url,
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
        if "cloud" in results and results["cloud"]:
            cloud_result = results["cloud"]
            refined_text = cloud_result["text"]
            description = cloud_result["description"]
            model_name_for_suffix = cloud_result.get(
                "model_name", "cloud_model"
            )  # Get actual model name

            # Extract model provider for the suffix, or use the model name
            model_provider = cloud_result.get("provider")
            if model_provider:
                model_suffix = model_provider
            elif model_name_for_suffix:
                model_suffix = model_name_for_suffix
            else:
                model_suffix = "cloud"  # Fallback suffix

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
                logger.debug(f"Saved cloud LLM result to: {saved_file_path}")
                saved_files.append(saved_file_path)

        # Save Ollama result if available
        if "ollama" in results and results["ollama"]:
            ollama_result = results["ollama"]
            ollama_refined_text = ollama_result["text"]
            ollama_description = ollama_result["description"]
            ollama_model_name_for_suffix = ollama_result.get(
                "model_name", "ollama_model"
            )  
            ollama_suffix = ollama_model_name_for_suffix

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
                logger.debug(f"Saved Ollama result to: {ollama_file_path}")
                saved_files.append(ollama_file_path)

        # Also return approximate word counts for downstream logic (e.g., Kindle auto-send)
        result = []
        for path in saved_files:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    text = f.read()
                # Remove YAML front matter (between first two ---) to get content word count
                if text.startswith('---'):
                    parts = text.split('---', 2)
                    if len(parts) == 3:
                        text_body = parts[2]
                    else:
                        text_body = text
                else:
                    text_body = text
                words = len(text_body.split())
            except Exception:
                words = 0
            result.append({'path': path, 'word_count': words})
        return result

    except Exception as e:
        # Log error message without stack trace
        error_msg = str(e).split("!")[0] if "!" in str(e) else str(e)
        logger.error(f"Error processing video {video_title}: {error_msg}")
        return None
