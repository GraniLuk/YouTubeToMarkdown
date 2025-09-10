import logging
import os
import sys
import textwrap
import winsound
from pathlib import Path

from dotenv import load_dotenv

from yt2md.cli import parse_args  # Import parse_args directly
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

    try:
        # Collect videos based on command line arguments
        if args.url:
            # Special Kindle fast-path: if --kindle and video already processed, resend without reprocessing
            if getattr(args, "kindle", False) and not args.skip_verification:
                from yt2md.youtube import extract_video_id, get_video_details_from_url
                from yt2md.video_index import get_processed_video_ids, find_markdown_files_for_video
                vid = extract_video_id(args.url)
                if vid:
                    processed_ids = get_processed_video_ids(False)
                    if vid in processed_ids:
                        logger.info(
                            "Video already processed; using existing markdown for Kindle delivery"
                        )
                        existing_files = find_markdown_files_for_video(vid)
                        if not existing_files:
                            logger.warning(
                                "No existing markdown files found despite index entry; falling back to reprocessing"
                            )
                        else:
                            # Choose most recent file
                            existing_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                            latest_md = existing_files[0]
                            try:
                                from yt2md.email.kindle import convert_md_to_epub, send_epub
                                epub_path = convert_md_to_epub(Path(latest_md))
                                recipient = os.getenv("KINDLE_EMAIL")
                                if recipient:
                                    ok = send_epub(epub_path, recipient, subject="Kindle Delivery", body="Resent existing note via --kindle fast path.")
                                    if ok:
                                        logger.info("Kindle resend successful")
                                    else:
                                        logger.error("Kindle resend failed")
                                else:
                                    logger.error("KINDLE_EMAIL not set; cannot resend")
                                return  # Skip normal processing path
                            except Exception as e:  # pragma: no cover
                                logger.error(f"Fast-path Kindle resend failed; will reprocess: {e}")
                # If fast path not taken, fall through to normal collection
            videos_to_process = collect_videos_from_url(
                args.url,
                language_code=args.language,
                skip_verification=args.skip_verification,
                category=args.category,
            )
        elif args.category:
            videos_to_process = collect_videos_from_category(
                args.category,
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

        results = process_videos(
            videos_to_process,
            use_ollama=args.ollama,
            use_cloud=args.cloud,
            skip_verification=args.skip_verification,
            ollama_model=ollama_model,
            ollama_base_url=ollama_base_url,
        )

        # Optional Kindle workflow: send newest note
        if getattr(args, "kindle", False):
            try:
                from yt2md.email.kindle import send_latest_markdown_to_kindle
                send_latest_markdown_to_kindle()
            except Exception as e:  # pragma: no cover
                logger.error(f"Kindle workflow error: {e}")

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
