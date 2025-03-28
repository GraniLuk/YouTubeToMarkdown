import argparse
import os
import os.path
import re
from datetime import datetime

from dotenv import load_dotenv

from yt2md.AI import analyze_transcript_with_gemini
from yt2md.config import load_channels
from yt2md.google_drive import setup_google_drive, upload_to_drive
from yt2md.youtube import (
    get_video_details_from_url,
    get_videos_from_channel,
    get_youtube_transcript,
)


def get_script_dir() -> str:
    """
    Get the directory where the script is located
    """
    return os.path.dirname(os.path.abspath(__file__))


# Load environment variables
env_path = os.path.join(get_script_dir(), ".env")
if not load_dotenv(env_path):
    raise Exception(f"Could not load .env file from {env_path}")

# Verify API keys are loaded
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise Exception("GEMINI_API_KEY not found in environment variables")


def save_to_markdown(
    title: str,
    video_url: str,
    refined_text: str,
    author: str,
    published_date: str,
    description: str,
) -> str:
    """
    Save refined text to a markdown file, update the video index, and upload to Google Drive.
    File will be saved in the path specified in SUMMARIES_PATH environment variable

    Args:
        title (str): YouTube video title
        video_url (str): YouTube video URL
        refined_text (str): Text to save
        author (str): Author of the video
        published_date (str): Published date of the video
        description (str): Description of the video

    Returns:
        str: Path to the saved file
    """
    try:
        # Get path from environment variable
        summaries_dir = os.getenv("SUMMARIES_PATH")
        if not summaries_dir:
            raise ValueError("SUMMARIES_PATH environment variable is not set")

        # Create directory if it doesn't exist
        os.makedirs(summaries_dir, exist_ok=True)

        # Clean the title to make it filesystem-friendly
        title = re.sub(r"[^\w\s-]", "", title)
        title = title.replace(" ", "_")

        # Add date prefix to filename
        today = datetime.now().strftime("%Y%m%d")
        filename = f"{today}-{title}.md"

        # Create full path
        filepath = os.path.join(summaries_dir, filename)

        # Get current date for 'created' field
        created_date = datetime.now().strftime("%Y-%m-%d")

        # Create the frontmatter
        frontmatter = f"""---
title: "{title}"
source: {video_url}
author: "[[{author}]]"
published: {published_date}
created: {created_date}
description: {description}
tags:
---

"""
        # Save to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter)
            f.write(refined_text)

        # Extract video ID from URL
        video_id = video_url.split("?v=")[1].split("&")[0]
        # Update index file inside the summaries directory
        index_file = os.path.join(summaries_dir, "video_index.txt")
        with open(index_file, "a", encoding="utf-8") as f:
            f.write(f"{video_id} | {filepath}\n")

        # After saving the file locally, upload to Google Drive
        try:
            drive_service = setup_google_drive()
            YOUTUBE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

            file_id = upload_to_drive(drive_service, filepath, YOUTUBE_FOLDER_ID)
            print(f"Uploaded to Google Drive with ID: {file_id}")
        except Exception as e:
            print(f"Warning: Failed to upload to Google Drive: {str(e)}")

        return os.path.abspath(filepath)

    except Exception as e:
        raise Exception(f"Error saving to markdown: {str(e)}")


def open_file(filepath: str):
    """
    Open a file using the default application on Windows.
    """
    try:
        os.startfile(filepath)
    except Exception as e:
        print(f"Failed to open file {filepath}: {str(e)}")


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
        choices=["IT", "Crypto", "AI"],
        help="Category of channels to process (IT, Crypto, or AI)",
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
