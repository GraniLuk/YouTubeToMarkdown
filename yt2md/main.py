import argparse
import os

from dotenv import load_dotenv

from yt2md.AI import analyze_transcript_with_gemini
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
if not api_key:
    raise Exception("GEMINI_API_KEY not found in environment variables")


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
        choices=["en", "pl"],
        help="Language code for the transcript (default: 'en' for English)",
    )
    args = parser.parse_args()

    try:
        if args.url:
            # Process single video
            # Extract video title using pytube
            video_url, video_title, published_date, channel_name = (
                get_video_details_from_url(args.url)
            )

            # Use the specified language for single video processing
            language_code = args.language
            output_language = (
                "English" if language_code == "en" else "Polish"
            )  # Determine output language based on input
            category = args.category

            print(f"Processing video: {video_title}")
            transcript = get_youtube_transcript(video_url, language_code=language_code)

            api_key = os.getenv("GEMINI_API_KEY")
            refined_text, description = analyze_transcript_with_gemini(
                transcript=transcript,
                api_key=api_key,
                model_name="gemini-2.5-pro-exp-03-25",
                output_language=output_language,
                category=category,
            )

            saved_file_path = save_to_markdown(
                video_title,
                video_url,
                refined_text,
                channel_name,
                published_date,
                description,
                category,
            )
            if saved_file_path:
                print(f"Saved to: {saved_file_path}")
                open_file(saved_file_path)
            return

        # Load channels from configuration
        channels = load_channels(args.category)

        if not channels:
            print(f"No channels found for category: {args.category}")
            return

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
            print(f"Processing video: {video_title}")

            try:
                # Get transcript with channel-specific language
                transcript = get_youtube_transcript(
                    video_url, language_code=channel.language_code
                )

                # Analyze with Gemini using channel-specific output language
                api_key = os.getenv("GEMINI_API_KEY")
                refined_text, description = analyze_transcript_with_gemini(
                    transcript=transcript,
                    api_key=api_key,
                    model_name="gemini-2.5-pro-exp-03-25",
                    output_language=channel.output_language,
                    category=channel.category,
                )

                # Save to markdown file
                saved_file_path = save_to_markdown(
                    video_title,
                    video_url,
                    refined_text,
                    channel.name,
                    published_date,
                    description,
                    channel.category,
                )
                if saved_file_path:
                    print(f"Saved to: {saved_file_path}")
                    open_file(saved_file_path)

            except Exception as e:
                print(f"Skipping video {video_title}: {str(e)}")
                continue

    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
