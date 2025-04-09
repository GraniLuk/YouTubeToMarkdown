import os
import re
from datetime import datetime, timedelta

import googleapiclient
import requests
from youtube_transcript_api import YouTubeTranscriptApi


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
    channel_id: str, days: int = 8, skip_verification: bool = False
) -> list[tuple[str, str, str]]:
    """
    Get all unprocessed videos from a YouTube channel published in the last days.
    Checks against video_index.txt to skip already processed videos.

    Args:
        channel_id (str): YouTube channel ID
        days (int): Number of days to look back
        skip_verification (bool): If True, skip checking if videos were already processed

    Returns:
        list[tuple[str, str]]: A list of tuples containing (video_url, video_title) for unprocessed videos
    """
    API_KEY = os.getenv("YOUTUBE_API_KEY")

    # Get processed video IDs from index file
    processed_video_ids = set()
    if not skip_verification:
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
                if not skip_verification and video_id in processed_video_ids:
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


def get_video_details_from_url(
    url: str, skip_verification: bool = False
) -> tuple[str, str, str, str]:
    """
    Get details for a YouTube video given its URL.

    Args:
        url (str): YouTube video URL
        skip_verification (bool): If True, skip checking if video was already processed

    Returns:
        list[tuple[str, str]]: A list of tuples containing (video_url, video_title) for unprocessed videos
    """
    API_KEY = os.getenv("YOUTUBE_API_KEY")

    # Get processed video IDs from index file
    processed_video_ids = set()
    if not skip_verification:
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
