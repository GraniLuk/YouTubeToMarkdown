"""Module for collecting videos from various sources like URLs or YouTube channels."""

import logging
from typing import List, Optional, Tuple

from yt2md.config import load_all_channels, load_channels_by_category
from yt2md.logger import get_logger
from yt2md.youtube import get_video_details_from_url, get_videos_from_channel

# Get logger for this module
logger = get_logger("video_collector")


def collect_videos_from_url(
    url: str,
    language_code: str = "en",
    skip_verification: bool = False,
    category: Optional[str] = None,
) -> List[Tuple]:
    """
    Collect video details from a specific URL.

    Args:
        url: YouTube video URL
        language_code: Language code for the transcript
        skip_verification: Whether to skip verification of already processed videos
        category: Optional category for the video

    Returns:
        List containing a single tuple with video details if successful, empty list otherwise
    """
    logger.info(f"Processing single video URL: {url}")
    video_details = get_video_details_from_url(url, skip_verification)

    if not video_details:
        logger.warning("Could not retrieve video details or video already processed")
        return []

    video_url, video_title, published_date, channel_name = video_details

    # Determine output language based on language code
    output_language = (
        "English"
        if language_code == "en"
        else "Spanish"
        if language_code == "es"
        else "Polish"
    )

    # Return as a list of one tuple for consistency with other collection methods
    return [
        (
            video_url,
            video_title,
            published_date,
            channel_name,
            language_code,
            output_language,
            category,
        )
    ]


def collect_videos_from_category(
    category: str, days: int, channel_name: Optional[str] = None
) -> List[Tuple]:
    """
    Collect videos from channels in a specified category.

    Args:
        category: Category name (IT, Crypto, AI, Fitness, Trading, News)
        days: Number of days to look back for videos
        channel_name: Optional specific channel name to filter within the category

    Returns:
        List of tuples with video details
    """
    logger.info(f"Processing videos from category: {category}")
    channels = load_channels_by_category(category)
    videos_to_process = []

    if not channels:
        logger.warning(f"No channels found for category: {category}")
        return videos_to_process

    # Filter by channel name if specified
    if channel_name:
        channels = [ch for ch in channels if ch.name.lower() == channel_name.lower()]
        if not channels:
            logger.warning(
                f"Channel '{channel_name}' not found in category '{category}'"
            )
            return videos_to_process
        logger.info(f"Processing channel: {channel_name} in {category} category...")
    else:
        logger.info(f"Processing {category} channels...")

    # Collect videos from all channels in the category
    for channel in channels:
        videos_to_process.extend(_collect_videos_from_single_channel(channel, days))

    return videos_to_process


def collect_videos_from_all_channels(days: int) -> List[Tuple]:
    """
    Collect videos from all configured channels.

    Args:
        days: Number of days to look back for videos

    Returns:
        List of tuples with video details
    """
    logger.info("Processing videos from all channels")
    channels = load_all_channels()
    videos_to_process = []

    for channel in channels:
        videos_to_process.extend(_collect_videos_from_single_channel(channel, days))

    return videos_to_process


def _collect_videos_from_single_channel(channel, days: int) -> List[Tuple]:
    """
    Helper function to collect videos from a single channel.

    Args:
        channel: Channel object with id, name, language_code, etc.
        days: Number of days to look back for videos

    Returns:
        List of tuples with video details
    """
    videos_to_process = []
    logger.debug(f"Getting videos from channel: {channel.name}")
    channel_videos = get_videos_from_channel(channel.id, days)
    logger.debug(
        f"Found {len(channel_videos)} videos from {channel.name} in the last {days} days"
    )

    for url, title, published_date in channel_videos:
        # Apply title filter if specified
        if channel.title_filters and not any(
            filter_text.lower() in title.lower()
            for filter_text in channel.title_filters
        ):
            logger.debug(
                f"Skipping video '{title}' as it does not match any title filters: {channel.title_filters}"
            )
            continue

        videos_to_process.append(
            (
                url,
                title,
                published_date,
                channel.name,
                channel.language_code,
                channel.output_language,
                channel.category,
            )
        )

    return videos_to_process
