"""Reporting utilities for displaying summaries and logs about video processing."""

from collections import defaultdict

import colorama

from yt2md.logger import colored_text, get_logger

# Get logger for this module
logger = get_logger("reporting")


def display_video_processing_summary(videos_to_process):
    """Display a summary of videos to be processed, grouped by category and author."""
    if not videos_to_process:
        logger.info("No videos to process.")
        return

    # Group videos by category and author
    videos_by_category = defaultdict(lambda: defaultdict(list))

    for video_url, video_title, _, channel_name, _, _, category in videos_to_process:
        category = category or "Uncategorized"
        videos_by_category[category][channel_name].append((video_title, video_url))

    # Display summary
    logger.info("=" * 60)
    logger.info("SUMMARY OF VIDEOS TO PROCESS:")
    logger.info("=" * 60)

    total_videos = 0
    for category, authors in sorted(videos_by_category.items()):
        category_count = sum(len(videos) for videos in authors.values())
        total_videos += category_count
        logger.info(f"\nCategory: {category} ({category_count} videos)")
        logger.info("-" * 50)

        for author, videos in sorted(authors.items()):
            logger.info(f"  Author: {author} ({len(videos)} videos)")

            for idx, (title, url) in enumerate(videos, 1):
                logger.info(f"    {idx}. {title}")
                logger.info(f"       {url}")

    logger.info("\n" + "=" * 60)
    logger.info(f"Total videos to process: {total_videos}")
    logger.info("=" * 60)

    return total_videos


def log_processing_time(execution_time):
    """Log the execution time in a formatted way."""
    minutes = int(execution_time // 60)
    seconds = execution_time % 60
    logger.info(
        colored_text(
            f"Processing completed in {minutes} min {seconds:.2f} sec",
            colorama.Fore.CYAN,
        )
    )
