import argparse
import logging
import os
import time
from collections import defaultdict

import colorama
from dotenv import load_dotenv

from yt2md.AI import analyze_transcript_by_length
from yt2md.config import load_all_channels, load_channels_by_category
from yt2md.file_operations import get_script_dir, save_to_markdown
from yt2md.logger import colored_text, get_logger, setup_logging
from yt2md.youtube import (
    get_video_details_from_url,
    get_videos_from_channel,
    get_youtube_transcript,
)

# Get logger for this module
logger = get_logger("main")

# Load environment variables
env_path = os.path.join(get_script_dir(), ".env")
if not load_dotenv(env_path):
    raise Exception(f"Could not load .env file from {env_path}")

# Verify API keys are loaded
api_key = os.getenv("GEMINI_API_KEY")
perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
if not api_key:
    raise Exception("GEMINI_API_KEY not found in environment variables")

# Perplexity API key is optional but recommended for fallback
if not perplexity_api_key:
    logger.warning(
        "PERPLEXITY_API_KEY not found. Fallback for rate limits won't be available."
    )

# Load Ollama configuration from environment variables
ollama_model = os.getenv("OLLAMA_MODEL", "gemma3:4b")
ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


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

    Returns:
        list: Paths to the saved file(s) or None if processing failed
    """
    try:
        logger.info(
            f"Processing video: {video_title} by {author_name} with URL: {video_url}"
        )
        saved_files = []

        # Get transcript
        transcript = get_youtube_transcript(video_url, language_code=language_code)
        if transcript is None:
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
        logger.error(f"Error processing video {video_title}: {str(e)}", exc_info=True)
        return None


def display_video_processing_summary(videos_to_process):
    """Display a summary of videos to be processed, grouped by category and author."""
    if not videos_to_process:
        logger.info("No videos to process.")
        return

    # Group videos by category and author
    videos_by_category = defaultdict(lambda: defaultdict(list))

    for video_url, video_title, _, channel_name, _, _, category in videos_to_process:
        category = category or "Uncategorized"
        videos_by_category[category][channel_name].append((video_title, video_url))

    # Display summary
    logger.info("=" * 60)
    logger.info("SUMMARY OF VIDEOS TO PROCESS:")
    logger.info("=" * 60)

    total_videos = 0
    for category, authors in sorted(videos_by_category.items()):
        category_count = sum(len(videos) for videos in authors.values())
        total_videos += category_count
        logger.info(f"\nCategory: {category} ({category_count} videos)")
        logger.info("-" * 50)

        for author, videos in sorted(authors.items()):
            logger.info(f"  Author: {author} ({len(videos)} videos)")

            for idx, (title, url) in enumerate(videos, 1):
                logger.info(f"    {idx}. {title}")
                logger.info(f"       {url}")

    logger.info("\n" + "=" * 60)
    logger.info(f"Total videos to process: {total_videos}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Process YouTube videos and create markdown summaries"
    )
    parser.add_argument(
        "--days", type=int, default=3, help="Number of days to look back for videos"
    )
    parser.add_argument(
        "--category",
        type=str,
        choices=["IT", "Crypto", "AI", "Fitness"],
        help="Category of channels to process (IT, Crypto, Fitness, or AI)",
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Process a specific YouTube video URL instead of channel videos",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en",
        choices=["en", "pl", "es"],
        help="Language code for the transcript (default: 'en' for English)",
    )
    parser.add_argument(
        "--channel",
        type=str,
        help="Process videos only from a specific channel name within the category",
    )
    parser.add_argument(
        "--ollama",
        action="store_true",
        help="Also process transcript with local Ollama LLM",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Force using cloud services only for transcript processing",
    )
    parser.add_argument(
        "--skip-verification",
        action="store_true",
        help="Skip checking if video was already processed and don't update index",
    )
    # Add logging related arguments
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output (DEBUG level)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress all output except errors (ERROR level)",
    )
    parser.add_argument("--log-file", type=str, help="Write logs to specified file")
    args = parser.parse_args()

    # Configure logging based on arguments
    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.ERROR

    setup_logging(level=log_level, log_file=args.log_file)

    videos_to_process = []  # List to hold all videos and their processing parameters

    try:
        if args.url:
            # Add single video to processing list
            logger.info(f"Processing single video URL: {args.url}")
            video_details = get_video_details_from_url(args.url, args.skip_verification)
            if not video_details:
                logger.warning(
                    "Could not retrieve video details or video already processed"
                )
                return

            video_url, video_title, published_date, channel_name = video_details

            # Use the specified language for single video processing
            language_code = args.language
            output_language = (
                "English"
                if language_code == "en"
                else "Spanish"
                if language_code == "es"
                else "Polish"
            )
            category = args.category

            # Add video to processing list
            videos_to_process.append(
                (
                    video_url,
                    video_title,
                    published_date,
                    channel_name,
                    language_code,
                    output_language,
                    category,
                )
            )

        elif args.category:
            # Process videos from channels in a category
            logger.info(f"Processing videos from category: {args.category}")
            channels = load_channels_by_category(args.category)

            if not channels:
                logger.warning(f"No channels found for category: {args.category}")
                return

            # Filter by channel name if specified
            if args.channel:
                channels = [
                    ch for ch in channels if ch.name.lower() == args.channel.lower()
                ]
                if not channels:
                    logger.warning(
                        f"Channel '{args.channel}' not found in category '{args.category}'"
                    )
                    return
                logger.info(
                    f"Processing channel: {args.channel} in {args.category} category..."
                )
            else:
                logger.info(f"Processing {args.category} channels...")

            # Collect videos from all channels
            for channel in channels:
                logger.debug(f"Getting videos from channel: {channel.name}")
                channel_videos = get_videos_from_channel(channel.id, args.days)
                logger.debug(
                    f"Found {len(channel_videos)} videos from {channel.name} in the last {args.days} days"
                )
                for url, title, published_date in channel_videos:
                    videos_to_process.append(
                        (
                            url,
                            title,
                            published_date,
                            channel.name,
                            channel.language_code,
                            channel.output_language,
                            channel.category,
                        )
                    )
        else:
            logger.info("Processing videos from all channels")
            channels = load_all_channels()
            for channel in channels:
                logger.debug(f"Getting videos from channel: {channel.name}")
                channel_videos = get_videos_from_channel(channel.id, args.days)
                logger.debug(
                    f"Found {len(channel_videos)} videos from {channel.name} in the last {args.days} days"
                )
                for url, title, published_date in channel_videos:
                    videos_to_process.append(
                        (
                            url,
                            title,
                            published_date,
                            channel.name,
                            channel.language_code,
                            channel.output_language,
                            channel.category,
                        )
                    )

        # Display summary of videos to process
        display_video_processing_summary(videos_to_process)

        logger.info(f"Total videos to process: {len(videos_to_process)}")

        # Process all collected videos
        for (
            video_url,
            video_title,
            published_date,
            channel_name,
            language_code,
            output_language,
            category,
        ) in videos_to_process:
            process_video(
                video_url,
                video_title,
                published_date,
                channel_name,
                language_code,
                output_language,
                category,
                use_ollama=args.ollama,
                use_cloud=args.cloud,
                skip_verification=args.skip_verification,
            )

    except Exception as e:
        logger.error(f"Error in main process: {str(e)}", exc_info=True)


if __name__ == "__main__":
    main()
