import logging
import os
import sys
import textwrap
import winsound

from dotenv import load_dotenv

from yt2md.cli import parse_args, parse_categories  # Import parse_args directly
from yt2md.file_operations import get_script_dir
from yt2md.logger import get_logger, setup_logging
from yt2md.reporting import display_video_processing_summary
from yt2md.video_collector import (
    collect_videos_from_all_channels,
    collect_videos_from_category,
    collect_videos_from_url,
)

# Get logger for this module
logger = get_logger("main")

# Load environment variables
env_path = os.path.join(get_script_dir(), ".env")
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(get_script_dir()), ".env")
load_dotenv(env_path)

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
ollama_model = os.getenv("OLLAMA_MODEL", "gemma4:26b")
ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def display_logo():
    """Display the YT2MD ASCII art logo with color."""
    RED = "\033[91m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"

    logo = textwrap.dedent(f"""{RED}
        
 __   _______ ___ __  __ ___  
 \\ \\ / /_   _|_  )  \\/  |   \\ 
  \\ V /  | |  / /| |\\/| | |) |
   |_|   |_| /___|_|  |_|___/ 
                              

{YELLOW}YouTube to Markdown Converter{RESET}
    """)
    print(logo)


def run_main(args):
    # Configure logging based on arguments
    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.ERROR

    setup_logging(level=log_level)

    videos_to_process = []  # List to hold all videos and their processing parameters
    categories = parse_categories(args.category)

    try:
        # Handle explicit podcast export mode
        podcast_mode = getattr(args, "podcast", False)
        if podcast_mode:
            from yt2md.podcast import process_podcast_download, process_podcast_subscriptions
            if args.url:
                process_podcast_download(args.url)
                return
            else:
                process_podcast_subscriptions(
                    days=args.days,
                    channel_name=args.channel,
                    max_videos=args.max_videos,
                )
                if not categories:
                    return

        # Automatically check and process podcast subscriptions in standard run
        elif not args.url and (not categories or "Podcast" in categories):
            try:
                from yt2md.config import load_channels_by_category
                if load_channels_by_category("Podcast"):
                    from yt2md.podcast import process_podcast_subscriptions
                    process_podcast_subscriptions(
                        days=args.days,
                        channel_name=args.channel,
                        max_videos=args.max_videos,
                    )
            except Exception as e:
                logger.warning(f"Podcast subscription processing warning: {e}")

        # Collect videos based on command line arguments
        if args.url:
            kindle_mode = getattr(args, "kindle", False)
            if kindle_mode and not args.skip_verification:
                try:
                    from yt2md.email.kindle import resend_latest_for_video_url
                    if resend_latest_for_video_url(args.url):
                        return  # Successfully resent existing note, stop.
                except Exception as e:  # pragma: no cover
                    logger.error(f"Kindle fast-path error (continuing to process): {e}")
            videos_to_process = collect_videos_from_url(
                args.url,
                language_code=args.language,
                skip_verification=args.skip_verification,
                category=categories[0] if categories else None,
            )
        elif categories:
            videos_to_process = collect_videos_from_category(
                categories,
                args.days,
                channel_name=args.channel,
                max_videos=args.max_videos,
            )
        else:
            videos_to_process = collect_videos_from_all_channels(
                args.days, max_videos=args.max_videos
            )

        # Display summary of videos to process
        display_video_processing_summary(videos_to_process)

        # Process all collected videos with progress
        from yt2md.processor import process_videos

        single_url_and_kindle = bool(args.url and getattr(args, "kindle", False))
        results = process_videos(
            videos_to_process,
            use_ollama=args.ollama,
            use_cloud=args.cloud,
            skip_verification=args.skip_verification,
            ollama_model=ollama_model,
            ollama_base_url=ollama_base_url,
            disable_kindle_auto=single_url_and_kindle,
            prefer_auto_generated=getattr(args, "auto_generated", False),
            force_openrouter=getattr(args, "openrouter", False),
            openrouter_model=getattr(args, "openrouter_model", None),
            skip_summarize_shorts=getattr(args, "skip_summarize_shorts", False),
        )

        # Kindle single URL explicit send (even if below threshold)
        if single_url_and_kindle and results:
            try:
                from yt2md.email.kindle import send_processed_results
                send_processed_results(results)
            except Exception as e:  # pragma: no cover
                logger.error(f"Kindle single url send error: {e}")

    # (Auto-send now handled immediately inside process_videos loop.)

        if os.name == "nt":  # Check if the platform is Windows
            winsound.Beep(1000, 500)
    except Exception as e:
        logger.error(f"Error in main process: {str(e)}", exc_info=True)


def main():
    """Main entry point for the application."""
    try:
        # Display welcome logo
        display_logo()

        # Parse command line arguments
        args = parse_args()

        # Run the application with parsed arguments
        run_main(args)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
