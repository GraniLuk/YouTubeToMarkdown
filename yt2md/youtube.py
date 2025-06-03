import os
import re
import time
from datetime import datetime, timedelta
from typing import Optional

import requests
from googleapiclient import discovery  # type: ignore
from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
from youtube_transcript_api._errors import (  # type: ignore
    NoTranscriptFound,
    TranscriptsDisabled,
    TranslationLanguageNotAvailable,
    VideoUnavailable,
)

from yt2md.logger import get_logger
from yt2md.video_index import get_processed_video_ids, update_video_index

# Get logger for this module
logger = get_logger("youtube")


def get_youtube_transcript(video_url: str, language_code: str = "en") -> Optional[str]:
    """
    Extract transcript from a YouTube video and return it as a string.

    Args:
        video_url (str): YouTube video URL
        language_code (str): Language code for the transcript (default: 'en' for English)

    Returns:
        str: Video transcript as a single string or None if transcript is not available
    """
    # Initialize video_id to None to ensure it's defined even if an exception occurs
    video_id = None

    max_retries = 3
    delay_seconds = 2
    for attempt in range(1, max_retries + 1):
        try:
            # Extract video ID from URL
            video_id = extract_video_id(url=video_url)
            if not video_id:
                logger.error(f"Failed to extract video ID from URL: {video_url}")
                return None
            logger.debug(
                f"Extracting transcript for video ID: {video_id} with language: {language_code} (attempt {attempt})"
            )

            # Get transcript with specified language
            transcript_list = YouTubeTranscriptApi.get_transcript(  # type: ignore
                video_id, languages=[language_code]
            )

            logger.debug(f"Retrieved {len(transcript_list)} transcript segments")  # type: ignore

            # Combine all transcript pieces into one string
            transcript = " ".join(
                [transcript["text"] for transcript in transcript_list]  # type: ignore
            )

            logger.debug(f"Transcript assembled with {len(transcript.split())} words")
            return transcript

        except VideoUnavailable:
            logger.error(
                f"No transcript available: Video {video_url} is unavailable (attempt {attempt})"
            )
            if video_id:
                try:
                    update_video_index(video_id, "VIDEO_UNAVAILABLE", False)
                except Exception as index_error:
                    logger.error(f"Failed to update video index: {str(index_error)}")
            return None

        except TranslationLanguageNotAvailable:
            logger.error(
                f"No transcript found for {video_url} in language '{language_code}' (attempt {attempt})"
            )
            return None

        except TranscriptsDisabled:
            logger.error(
                f"Transcripts are disabled for video {video_url} (attempt {attempt})"
            )
            if video_id:
                try:
                    update_video_index(video_id, "TRANSCRIPTS_DISABLED", False)
                    logger.info(
                        f"Added video {video_id} to index as TRANSCRIPTS_DISABLED"
                    )
                except Exception as index_error:
                    logger.error(f"Failed to update video index: {str(index_error)}")
            return None

        except NoTranscriptFound:
            logger.error(
                f"No transcripts available for video {video_url} (attempt {attempt})"
            )
            if video_id:
                try:
                    update_video_index(video_id, "NO_TRANSCRIPT_FOUND", False)
                    logger.info(
                        f"Added video {video_id} to index as NO_TRANSCRIPT_FOUND"
                    )
                except Exception as index_error:
                    logger.error(f"Failed to update video index: {str(index_error)}")
            return None

        except Exception as e:
            # Check for VideoUnplayable error message pattern
            if "The video is unplayable for the following reason:" in str(e):
                reason = (
                    str(e)
                    .split("The video is unplayable for the following reason:")[1]
                    .split("\n")[1]
                    .strip()
                )
                logger.error(
                    f"No transcript available for {video_url}: {reason} (attempt {attempt})"
                )
                if video_id:
                    try:
                        update_video_index(video_id, "VIDEO_UNPLAYABLE", False)
                    except Exception as index_error:
                        logger.error(
                            f"Failed to update video index: {str(index_error)}"
                        )
                return None

            # Handle other exceptions
            logger.debug(
                f"Transcript extraction error for {video_url} (attempt {attempt}): {str(e)}"
            )
            if attempt < max_retries:
                logger.debug(
                    f"Retrying transcript extraction for {video_url} in {delay_seconds} seconds..."
                )
                time.sleep(delay_seconds)
            else:
                logger.error(
                    f"All {max_retries} attempts failed for {video_url}. Last error: {str(e)}"
                )
                return None


def get_videos_from_channel(
    channel_id: str,
    days: int = 8,
    skip_verification: bool = False,
    max_pages: int = 100,  # Default to a high number to keep paginating
    max_videos: int = 10,
) -> list[tuple[str, str, str]]:
    """
    Get all unprocessed videos from a YouTube channel published in the last days.
    Checks against video_index.txt to skip already processed videos.

    Args:
        channel_id (str): YouTube channel ID
        days (int): Number of days to look back
        skip_verification (bool): If True, skip checking if videos were already processed
        max_pages (int): Maximum number of API result pages to fetch (default: 100)
        max_videos (int): Maximum number of videos to collect per channel (default: 10)

    Returns:
        list[tuple[str, str, str]]: A list of tuples containing (video_url, video_title, published_date) for each video
    """
    API_KEY = os.getenv("YOUTUBE_API_KEY")
    logger.debug(
        f"Fetching videos from channel ID: {channel_id} for last {days} days (max {max_videos} videos)"
    )

    # Get processed video IDs from index file
    processed_video_ids = get_processed_video_ids(skip_verification)
    logger.debug(f"Found {len(processed_video_ids)} already processed videos")

    end_date = datetime.now()
    start_date = (end_date - timedelta(days=days)).isoformat("T") + "Z"
    logger.debug(f"Searching for videos published after {start_date}")

    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&type=video&order=date&publishedAfter={start_date}&key={API_KEY}&maxResults=50"

    videos: list[tuple[str, str, str]] = []
    next_page_token = None
    page_count = 0
    api_calls_count = 0

    # Fetch pages up to max_pages limit or until we have max_videos
    while page_count < max_pages and len(videos) < max_videos:
        page_count += 1
        api_calls_count += 1

        if next_page_token:
            current_url = f"{url}&pageToken={next_page_token}"
            logger.debug(f"Fetching page {page_count} with token: {next_page_token}")
        else:
            current_url = url
            logger.debug("Fetching first page of results")

        try:
            response = requests.get(current_url)
            data = response.json()

            if "error" in data:
                logger.error(f"YouTube API error: {data['error']['message']}")
                break

            if "items" in data:
                items_count = len(data["items"])
                logger.debug(f"Retrieved {items_count} videos on page {page_count}")

                for item in data["items"]:
                    # Stop if we've reached the maximum videos limit
                    if len(videos) >= max_videos:
                        logger.info(
                            f"Reached maximum videos limit ({max_videos}) for channel {channel_id}"
                        )
                        break

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
                break  # Break if no items found to avoid unnecessary API calls

            # Check if we need to fetch more pages
            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                logger.debug("No more pages to fetch")
                break

            # If we've collected enough videos, stop fetching more pages
            if len(videos) >= max_videos:
                logger.info(f"Collected {len(videos)} videos, stopping pagination")
                break

        except Exception as e:
            logger.error(
                f"Error fetching videos from channel {channel_id}: {str(e)}",
                exc_info=True,
            )
            break

    logger.debug(
        f"Made {api_calls_count} API calls for channel {channel_id}, collected {len(videos)} videos"
    )
    return videos


def extract_video_id(url: str) -> Optional[str]:
    # Extract video ID from different YouTube URL formats
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None


def get_video_details_from_url(
    url: str, skip_verification: bool = False
) -> Optional[tuple[str, str, str, str]]:
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
    if video_id in processed_video_ids:
        logger.debug(f"Video with ID {video_id} was already processed. Skipping...")
        return None

    try:
        # Initialize YouTube API client
        youtube = discovery.build("youtube", "v3", developerKey=API_KEY)  # type: ignore
        logger.debug("YouTube API client initialized")

        # Request video details
        request = youtube.videos().list(part="snippet", id=video_id)  # type: ignore
        data = request.execute()  # type: ignore
        logger.debug("YouTube API request executed")

        if "items" in data and data["items"]:
            firstItem = data["items"][0]  # type: ignore
            if firstItem:
                snippet = firstItem["snippet"]  # type: ignore
                title = snippet["title"]  # type: ignore
                published_date = snippet["publishedAt"].split("T")[  # type: ignore
                    0
                ]  # Get just the date
                channel_name = snippet["channelTitle"]  # type: ignore
                logger.debug(
                    f"Retrieved details for video '{title}' published on {published_date} by {channel_name}"
                )
                return (url, title, published_date, channel_name)  # type: ignore
        else:
            logger.error(f"No video details found for URL: {url}")
    except Exception as e:
        logger.error(f"Error getting video details for URL {url}: {str(e)}")

    return None
