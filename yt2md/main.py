import argparse
import os
import time  # Add time module import

from dotenv import load_dotenv

from yt2md.AI import analyze_transcript_by_length
from yt2md.config import load_channels
from yt2md.file_operations import get_script_dir, open_file, save_to_markdown
from yt2md.youtube import (
    get_video_details_from_url,
    get_videos_from_channel,
    get_youtube_transcript,
)

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
    print(
        "Warning: PERPLEXITY_API_KEY not found. Fallback for rate limits won't be available."
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
        print(f"Processing video: {video_title}")
        saved_files = []

        # Get transcript
        transcript = get_youtube_transcript(video_url, language_code=language_code)
        print(f"Transcript length: {len(transcript.split())} words")

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
        print(f"Transcript analysis completed in {minutes} min {seconds:.2f} sec")

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
                print(f"Saved cloud LLM result to: {saved_file_path}")
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
                print(f"Saved Ollama result to: {ollama_file_path}")
                saved_files.append(ollama_file_path)

        return saved_files

    except Exception as e:
        print(f"Error processing video {video_title}: {str(e)}")
        return None


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
    args = parser.parse_args()

    try:
        if args.url:
            # Process single video
            video_details = get_video_details_from_url(args.url, args.skip_verification)
            if not video_details:
                print("Could not retrieve video details or video already processed")
                return

            video_url, video_title, published_date, channel_name = video_details

            # Use the specified language for single video processing
            language_code = args.language
            output_language = "English" if language_code == "en" else "Spanish" if language_code == "es" else "Polish"
            category = args.category

            # Process the video using our common function
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
            return

        # Process videos from channels in a category
        channels = load_channels(args.category)

        if not channels:
            print(f"No channels found for category: {args.category}")
            return

        # Filter by channel name if specified
        if args.channel:
            channels = [
                ch for ch in channels if ch.name.lower() == args.channel.lower()
            ]
            if not channels:
                print(
                    f"Channel '{args.channel}' not found in category '{args.category}'"
                )
                return
            print(f"Processing channel: {args.channel} in {args.category} category...")
        else:
            print(f"Processing {args.category} channels...")

        videos = []
        for channel in channels:
            channel_videos = get_videos_from_channel(channel.id, args.days)
            videos.extend(
                [
                    (url, title, published_date, channel)
                    for url, title, published_date in channel_videos
                ]
            )

        for video_url, video_title, published_date, channel in videos:
            # Process the video using our common function
            process_video(
                video_url,
                video_title,
                published_date,
                channel.name,
                channel.language_code,
                channel.output_language,
                channel.category,
                use_ollama=args.ollama,
                use_cloud=args.cloud,
                skip_verification=args.skip_verification,
            )

    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
