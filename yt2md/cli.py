import argparse


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
        choices=["IT", "Crypto", "AI", "Fitness", "Trading", "News"],
        help="Category of channels to process (IT, Crypto, Fitness, Trading, News or AI)",
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
    parser.add_argument(
        "--max-videos",
        type=int,
        default=10,
        help="Maximum number of videos to collect per channel (default: 10)",
    )
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
    parser.add_argument(
        "--kindle",
        action="store_true",
        help="After generating a note, convert latest markdown to EPUB and email it as attachment",
    )
    parser.add_argument(
        "--auto-generated",
        action="store_true",
        help="Prefer auto-generated transcripts over manual ones (useful when manual subtitles are corrupted)",
    )
    return parser


def parse_args(args=None):
    """Parse command line arguments."""
    parser = create_parser()
    return parser.parse_args(args)


def main():
    """Entry point for the CLI command.
    Parses arguments and delegates to main module for execution.
    """
    from yt2md.main import display_logo, run_main

    # Display the welcome logo
    display_logo()

    args = parse_args()
    run_main(args)
