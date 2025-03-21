import argparse
import os
import os.path
import pickle
import re
from datetime import datetime, timedelta

import googleapiclient
import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

from yt2md.AI import analyze_transcript_with_gemini
from yt2md.channel import Channel
from yt2md.google_drive import upload_to_drive


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


def get_script_dir() -> str:
    """
    Get the directory where the script is located
    """
    return os.path.dirname(os.path.abspath(__file__))


def get_youtube_transcript(video_url: str, language_code: str = "en") -> str:
    """
    Extract transcript from a YouTube video and return it as a string.

    Args:
        video_url (str): YouTube video URL
        language_code (str): Language code for the transcript (default: 'pl' for Polish)

    Returns:
        str: Video transcript as a single string
    """
    try:
        # Extract video ID from URL
        video_id = video_url.split("?v=")[1].split("&")[0]

        # Get transcript with specified language
        transcript_list = YouTubeTranscriptApi.get_transcript(
            video_id, languages=[language_code]
        )

        # Combine all transcript pieces into one string
        transcript = " ".join([transcript["text"] for transcript in transcript_list])

        return transcript

    except Exception as e:
        raise Exception(f"Transcript extraction error: {str(e)}")


def get_videos_from_channel(
    channel_id: str, days: int = 8
) -> list[tuple[str, str, str]]:
    """
    Get all unprocessed videos from a YouTube channel published in the last days.
    Checks against video_index.txt to skip already processed videos.

    Args:
        channel_id (str): YouTube channel ID

    Returns:
        list[tuple[str, str]]: A list of tuples containing (video_url, video_title) for unprocessed videos
    """
    API_KEY = os.getenv("YOUTUBE_API_KEY")

    # Get processed video IDs from index file
    processed_video_ids = set()
    summaries_dir = os.getenv("SUMMARIES_PATH")
    if not summaries_dir:
        raise ValueError("SUMMARIES_PATH environment variable is not set")

    index_file = os.path.join(summaries_dir, "video_index.txt")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            processed_video_ids = {
                line.split(" | ")[0].strip() for line in f if line.strip()
            }

    # Calculate the datetime 24 hours ago
    end_date = datetime.now()
    start_date = (end_date - timedelta(days=days)).isoformat("T") + "Z"

    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&type=video&order=date&publishedAfter={start_date}&key={API_KEY}&maxResults=50"

    videos = []
    next_page_token = None

    while True:
        if next_page_token:
            current_url = f"{url}&pageToken={next_page_token}"
        else:
            current_url = url

        response = requests.get(current_url)
        data = response.json()

        if "items" in data:
            for item in data["items"]:
                video_id = item["id"]["videoId"]
                if video_id in processed_video_ids:
                    print(
                        f"Video {item['snippet']['title']} was already processed. Skipping..."
                    )
                    continue

                video_url = f"https://www.youtube.com/watch?v={video_id}"
                title = item["snippet"]["title"]
                published_date = item["snippet"]["publishedAt"].split("T")[
                    0
                ]  # Get just the date part
                videos.append((video_url, title, published_date))

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break
    return videos


def extract_video_id(url):
    # Extract video ID from different YouTube URL formats
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None


def get_video_details_from_url(url: str) -> tuple[str, str, str, str]:
    """
    Get details for a YouTube video given its URL.

    Args:
        url (str): YouTube video URL

    Returns:
        list[tuple[str, str]]: A list of tuples containing (video_url, video_title) for unprocessed videos
    """
    API_KEY = os.getenv("YOUTUBE_API_KEY")

    # Get processed video IDs from index file
    processed_video_ids = set()
    summaries_dir = os.getenv("SUMMARIES_PATH")
    if not summaries_dir:
        raise ValueError("SUMMARIES_PATH environment variable is not set")

    index_file = os.path.join(summaries_dir, "video_index.txt")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            processed_video_ids = {
                line.split(" | ")[0].strip() for line in f if line.strip()
            }

        # Extract video ID from URL
        video_id = extract_video_id(url)
        if not video_id:
            return "Invalid YouTube URL"

        # Check if the video ID is already processed
        if video_id in processed_video_ids:
            print(f"Video with ID {video_id} was already processed. Skipping...")
            return None

        # Initialize YouTube API client
        youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=API_KEY)

        # Request video details
        request = youtube.videos().list(part="snippet", id=video_id)
        data = request.execute()

        if "items" in data:
            firstItem = data["items"][0]
            if firstItem:
                video_url = url
                title = firstItem["snippet"]["title"]
                published_date = firstItem["snippet"]["publishedAt"].split("T")[
                    0
                ]  # Get just the date part
                channel_name = firstItem["snippet"]["channelTitle"]
                return (video_url, title, published_date, channel_name)
        return None
    return None


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


def setup_google_drive():
    """
    Sets up Google Drive API credentials
    Returns:
        Google Drive API service
    """
    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    creds = None
    script_dir = get_script_dir()
    token_path = os.path.join(script_dir, "token.pickle")
    credentials_path = os.path.join(script_dir, "credentials.json")

    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                os.remove(token_path)
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=8080)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(
                port=8080, access_type="offline", include_granted_scopes="true"
            )
        # Save the credentials for the next run
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return build("drive", "v3", credentials=creds)


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
                model_name="gemini-2.0-pro-exp-02-05",
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

        # Rest of the existing channel processing code
        # Define channels with their language settings and categories
        all_channels = [
            # IT Channels
            Channel(
                "UCrkPsvLGln62OMZRO6K-llg", "en", "English", "IT", "Nick Chapsas"
            ),  # Nick Chapsas
            Channel(
                "UCC_dVe-RI-vgCZfls06mDZQ", "en", "English", "IT", "Milan Jovanovic"
            ),  # Milan Jovanovic
            Channel(
                "UCidgSn6WJ9Fv3kwUtoI7_Jg", "en", "English", "IT", "Stefan Dokic"
            ),  # Stefan Dokic
            Channel(
                "UCX189tVw5L1E0uRpzJgj8mQ", "pl", "Polish", "IT", "DevMentors"
            ),  # DevMentors
            Channel(
                "UC3RKA4vunFAfrfxiJhPEplw", "en", "English", "IT", "CodeOpinion"
            ),  # CodeOpinion
            # Crypto Channels - Add your crypto channels here
            # Channel("UCBIt1VN5j37PVM8LLSuTTlw", "en", "English", "Crypto", "Coin Bureau"),  # Coin Bureau
            # Channel("UCqK_GSMbpiV8spgD3ZGloSw", "en", "English", "Crypto", "Crypto Banter"),  # Crypto Banter
            Channel(
                "UCsaWU2rEXFkufFN_43jH2MA", "pl", "Polish", "Crypto", "Jarzombek"
            ),  # Jarzombek
            Channel(
                "UCXasJkcS9vY8X4HgzReo10A", "pl", "Polish", "Crypto", "Ostapowicz"
            ),  # Ostapowicz
            Channel(
                "UCKy4pRGNqVvpI6HrO9lo3XA", "pl", "Polish", "Crypto", "Krypto Raport"
            ),  # Krypto Raport
            Channel(
                "UCWTpgi3bE5gIVfhEys-T12A", "pl", "Polish", "AI", "Mike Tomala"
            ),  # Mike Tomala
            Channel(
                "UCgfISCCaUB4zMyD8uvx56jw", "en", "English", "AI", "Ben's Cyber Life"
            ),  # Ben's Cyber Life
            Channel(
                "UCXUPKJO5MZQN11PqgIvyuvQ", "en", "English", "AI", "Andrej Karpathy"
            ),  # Andrej Karpathy
            Channel(
                "UC55ODQSvARtgSyc8ThfiepQ", "en", "English", "AI", "Sam Witteveen"
            ),  # Sam Witteveen,
            Channel(
                "UChpleBmo18P08aKCIgti38g", "en", "English", "AI", "Matt Wolfe"
            ),  # Matt Wolfe
            Channel(
                "UCsBjURrPoezykLs9EqgamOA", "en", "English", "AI", "Fireship"
            ),  # Fireship
        ]

        # Filter channels based on selected category
        channels = [
            channel for channel in all_channels if channel.category == args.category
        ]

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

            # Get transcript with channel-specific language
            transcript = get_youtube_transcript(
                video_url, language_code=channel.language_code
            )

            # Analyze with Gemini using channel-specific output language
            api_key = os.getenv("GEMINI_API_KEY")
            refined_text, description = analyze_transcript_with_gemini(
                transcript=transcript,
                api_key=api_key,
                model_name="gemini-2.0-pro-exp-02-05",
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
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
