import os
import re
from datetime import datetime, timedelta

import googleapiclient
import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    TranslationLanguageNotAvailable,
    VideoUnplayable,
)

from yt2md.logger import get_logger
from yt2md.video_index import get_processed_video_ids, update_video_index

# Get logger for this module
logger = get_logger("youtube")


def get_youtube_transcript(video_url: str, language_code: str = "en") -> str:
    """
    Extract transcript from a YouTube video and return it as a string.

    Args:
        video_url (str): YouTube video URL
        language_code (str): Language code for the transcript (default: 'en' for English)

    Returns:
        str: Video transcript as a single string or None if transcript is not available
    """
    try:
        # Extract video ID from URL
        video_id = video_url.split("?v=")[1].split("&")[0]

        logger.debug(
            f"Extracting transcript for video ID: {video_id} with language: {language_code}"
        )

        # Get transcript with specified language
        transcript_list = YouTubeTranscriptApi.get_transcript(
            video_id, languages=[language_code]
        )

        logger.debug(f"Retrieved {len(transcript_list)} transcript segments")

        # Combine all transcript pieces into one string
        transcript = " ".join([transcript["text"] for transcript in transcript_list])

        logger.debug(f"Transcript assembled with {len(transcript.split())} words")
        return transcript

    except VideoUnplayable:
        # Handle scheduled live videos or other unplayable videos without stack trace
        logger.error(
            f"No transcript available for {video_url}: Video is unplayable (possibly a scheduled live event)"
        )
        return None
    except TranslationLanguageNotAvailable:
        # Handle when transcript is not available in the requested language
        logger.error(
            f"No transcript found for {video_url} in language '{language_code}'. Try a different language."
        )
        return None
    except TranscriptsDisabled:
        # Handle when transcripts are disabled for the video
        logger.error(f"Transcripts are disabled for video {video_url}")

        # Use the already extracted video_id to add to the index
        try:
            # Add to index with special marker to indicate transcripts are disabled
            update_video_index(video_id, "TRANSCRIPTS_DISABLED", False)
            logger.info(f"Added video {video_id} to index as TRANSCRIPTS_DISABLED")
        except Exception as index_error:
            logger.error(f"Failed to update video index: {str(index_error)}")

        return None
    except NoTranscriptFound:
        # Handle when no transcripts are available at all
        logger.error(f"No transcripts available for video {video_url}")
        return None
    except Exception as e:
        logger.error(f"Transcript extraction error for {video_url}: {str(e)}")
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
        tuple[str, str, str, str]: A tuple containing (video_url, video_title, published_date, channel_name) for the video
    """
    API_KEY = os.getenv("YOUTUBE_API_KEY")
    logger.debug(f"Fetching videos from channel ID: {channel_id} for last {days} days")

    # Get processed video IDs from index file
    processed_video_ids = get_processed_video_ids(skip_verification)
    logger.debug(f"Found {len(processed_video_ids)} already processed videos")

    # Calculate the datetime 24 hours ago
    end_date = datetime.now()
    start_date = (end_date - timedelta(days=days)).isoformat("T") + "Z"
    logger.debug(f"Searching for videos published after {start_date}")

    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&type=video&order=date&publishedAfter={start_date}&key={API_KEY}&maxResults=50"

    videos = []
    next_page_token = None
    page_count = 0

    while True:
        page_count += 1
        if next_page_token:
            current_url = f"{url}&pageToken={next_page_token}"
            logger.debug(f"Fetching page {page_count} with token: {next_page_token}")
        else:
            current_url = url
            logger.debug(f"Fetching first page of results")

        try:
            response = requests.get(current_url)
            data = response.json()

            if "error" in data:
                logger.error(f"YouTube API error: {data['error']['message']}")
                break

            if "items" in data:
                logger.debug(
                    f"Retrieved {len(data['items'])} videos on page {page_count}"
                )
                for item in data["items"]:
                    video_id = item["id"]["videoId"]
                    if not skip_verification and video_id in processed_video_ids:
                        logger.debug(
                            f"Video {item['snippet']['title']} was already processed. Skipping..."
                        )
                        continue

                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    title = item["snippet"]["title"]
                    published_date = item["snippet"]["publishedAt"].split("T")[
                        0
                    ]  # Get just the date part
                    logger.debug(f"Adding video: {title} ({published_date})")
                    videos.append((video_url, title, published_date))
            else:
                logger.warning("No items found in YouTube API response")

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                logger.debug("No more pages to fetch")
                break
        except Exception as e:
            logger.error(
                f"Error fetching videos from channel {channel_id}: {str(e)}",
                exc_info=True,
            )
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
        tuple[str, str, str, str] or None: A tuple containing (video_url, video_title, published_date, channel_name) or None if an error occurs
    """
    API_KEY = os.getenv("YOUTUBE_API_KEY")
    logger.debug(f"Getting video details for URL: {url}")

    # Extract video ID from URL
    video_id = extract_video_id(url)
    if not video_id:
        logger.error(f"Invalid YouTube URL: {url}")
        return None

    logger.debug(f"Extracted video ID: {video_id}")

    # Get processed video IDs from index file
    processed_video_ids = get_processed_video_ids(skip_verification)

    # Check if the video ID is already processed
    if video_id in processed_video_ids:
        logger.debug(f"Video with ID {video_id} was already processed. Skipping...")
        return None

    try:
        # Initialize YouTube API client
        youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=API_KEY)
        logger.debug("YouTube API client initialized")

        # Request video details
        request = youtube.videos().list(part="snippet", id=video_id)
        data = request.execute()
        logger.debug("YouTube API request executed")

        if "items" in data and data["items"]:
            firstItem = data["items"][0]
            if firstItem:
                video_url = url
                title = firstItem["snippet"]["title"]
                published_date = firstItem["snippet"]["publishedAt"].split("T")[
                    0
                ]  # Get just the date part
                channel_name = firstItem["snippet"]["channelTitle"]
                logger.info(
                    f"Retrieved details for video: {title} from channel {channel_name}"
                )
                return (video_url, title, published_date, channel_name)
        else:
            logger.warning(f"No video details found for ID: {video_id}")
    except Exception as e:
        logger.error(f"Error getting video details for {url}: {str(e)}", exc_info=True)

    return None
