import argparse
import sys

from yt2md.main import main as yt2md_main


def create_parser():
    """Create the command line argument parser."""
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
    return parser


def parse_args(args=None):
    """Parse command line arguments."""
    parser = create_parser()
    return parser.parse_args(args)


def main():
    try:
        yt2md_main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
