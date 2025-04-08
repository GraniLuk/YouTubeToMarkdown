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
        default="IT",
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
        choices=["en", "pl"],
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
        "--ollama-model",
        type=str,
        default="mistral",
        help="Model name to use with Ollama (default: mistral)",
    )
    parser.add_argument(
        "--ollama-host",
        type=str,
        default="http://localhost",
        help="Host address for Ollama API (default: http://localhost)",
    )
    parser.add_argument(
        "--ollama-port",
        type=int,
        default=11434,
        help="Port for Ollama API (default: 11434)",
    )

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
