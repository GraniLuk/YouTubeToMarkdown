import logging
import os
import sys
import textwrap
import winsound

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

        process_videos(
            videos_to_process,
            use_ollama=args.ollama,
            use_cloud=args.cloud,
            skip_verification=args.skip_verification,
            ollama_model=ollama_model,
            ollama_base_url=ollama_base_url,
        )

        # Optional Kindle workflow: convert latest generated markdown to EPUB and email
        if getattr(args, "kindle", False):
            try:
                summaries_dir = os.getenv("SUMMARIES_PATH")
                if not summaries_dir:
                    logger.error("SUMMARIES_PATH not set; cannot perform --kindle workflow")
                    return

                # Gather all markdown files recursively
                md_files = []
                for root, _dirs, files in os.walk(summaries_dir):
                    for f in files:
                        if f.lower().endswith(".md"):
                            full_path = os.path.join(root, f)
                            md_files.append(full_path)

                if not md_files:
                    logger.warning("No markdown files found for --kindle workflow")
                    return

                # Sort by modification time descending
                md_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                latest_md = md_files[0]
                logger.info(f"Latest markdown selected for Kindle workflow: {latest_md}")

                # Convert to EPUB (same directory, same stem)
                try:
                    from yt2md.email.epub.converter import md_to_epub, EpubOptions
                except Exception as e:  # pragma: no cover
                    logger.error(f"EPUB converter import failed: {e}")
                    return

                epub_path = None
                try:
                    epub_path = md_to_epub(latest_md, options=EpubOptions())
                except Exception as e:
                    logger.error(f"EPUB conversion failed: {e}")
                    return

                logger.info(f"Generated EPUB: {epub_path}")

                # Email parameters
                recipient = os.getenv("KINDLE_EMAIL")
                if not recipient:
                    logger.error("No Kindle recipient email set (KINDLE_EMAIL)")
                    return

                subject = f"Kindle Delivery: {os.path.splitext(os.path.basename(latest_md))[0]}"
                body = "Automated delivery from yt2md --kindle workflow."

                try:
                    from yt2md.email.send_email import send_email
                except Exception as e:  # pragma: no cover
                    logger.error(f"Email sender import failed: {e}")
                    return

                sent = send_email(
                    subject=subject,
                    body=body,
                    recipients=recipient,
                    attachments=[str(epub_path)] if epub_path else None,
                )
                if sent:
                    logger.info("Kindle email sent successfully")
                else:
                    logger.error("Failed to send Kindle email")
            except Exception as e:  # pragma: no cover
                logger.error(f"Unhandled --kindle workflow error: {e}")

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
