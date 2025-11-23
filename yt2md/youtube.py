import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
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

from yt2md.audio_fallback import extract_transcript_via_audio, is_fallback_enabled
from yt2md.logger import get_logger
from yt2md.video_index import get_processed_video_ids, update_video_index

# Get logger for this module
logger = get_logger("youtube")

# Fallback-only mode state (activated after consecutive failures or IP blocks)
_fallback_only_mode = False
_consecutive_failures = 0
_CONSECUTIVE_FAILURES_THRESHOLD = int(os.getenv("CONSECUTIVE_FAILURES_THRESHOLD", "3"))

_DURATION_PATTERN = re.compile(
    r"PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)

_UPLOADS_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "config", "youtube_uploads_cache.json"
)
_uploads_playlist_cache: dict[str, str] = {}
_uploads_cache_loaded = False
_uploads_cache_dirty = False

_YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
_DEFAULT_REQUEST_TIMEOUT = 15
_RATE_LIMIT_SLEEP_SECONDS = 0.2


def _load_uploads_playlist_cache() -> None:
    global _uploads_cache_loaded, _uploads_playlist_cache
    if _uploads_cache_loaded:
        return

    try:
        with open(_UPLOADS_CACHE_FILE, "r", encoding="utf-8") as cache_file:
            data = json.load(cache_file)
            if isinstance(data, dict):
                _uploads_playlist_cache = {
                    str(key): str(value) for key, value in data.items()
                }
                logger.debug(
                    "Loaded %d cached upload playlist ids", len(_uploads_playlist_cache)
                )
    except FileNotFoundError:
        logger.debug(
            "Uploads playlist cache file not found. It will be created on save."
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.warning("Failed to load uploads playlist cache: %s", str(exc))

    _uploads_cache_loaded = True


def _save_uploads_playlist_cache() -> None:
    global _uploads_cache_dirty
    if not _uploads_cache_dirty:
        return

    try:
        os.makedirs(os.path.dirname(_UPLOADS_CACHE_FILE), exist_ok=True)
        with open(_UPLOADS_CACHE_FILE, "w", encoding="utf-8") as cache_file:
            json.dump(_uploads_playlist_cache, cache_file, ensure_ascii=False, indent=2)
        logger.debug(
            "Persisted %d upload playlist ids to cache file",
            len(_uploads_playlist_cache),
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.error("Failed to persist uploads playlist cache: %s", str(exc))
    finally:
        _uploads_cache_dirty = False


def _request_json(url: str, params: Optional[dict[str, str]] = None) -> dict:
    time.sleep(_RATE_LIMIT_SLEEP_SECONDS)
    response = requests.get(url, params=params, timeout=_DEFAULT_REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _extract_youtube_error_message(error: requests.HTTPError) -> str:
    try:
        payload = error.response.json() if error.response is not None else None
        message = payload.get("error", {}).get("message") if payload else None
        if message:
            return message
    except Exception:  # pragma: no cover - defensive parsing only
        pass
    return str(error)


def _get_uploads_playlist_id(channel_id: str, api_key: Optional[str]) -> Optional[str]:
    """Resolve the uploads playlist ID for a channel, caching the result locally."""
    if not api_key:
        logger.error("YOUTUBE_API_KEY is not set. Cannot resolve uploads playlist id.")
        return None

    _load_uploads_playlist_cache()
    if channel_id in _uploads_playlist_cache:
        return _uploads_playlist_cache[channel_id]

    params = {
        "part": "contentDetails",
        "id": channel_id,
        "key": api_key,
        "maxResults": "1",
    }

    try:
        data = _request_json(f"{_YOUTUBE_API_BASE}/channels", params=params)
    except requests.HTTPError as http_exc:
        logger.error(
            "YouTube API error resolving uploads playlist for channel %s: %s",
            channel_id,
            str(http_exc),
        )
        return None
    except Exception as exc:  # pragma: no cover - network errors are rare/hard to mock
        logger.error(
            "Unexpected error resolving uploads playlist for channel %s: %s",
            channel_id,
            str(exc),
        )
        return None

    items = data.get("items") or []
    if not items:
        logger.error("No uploads playlist found for channel %s", channel_id)
        return None

    content_details = items[0].get("contentDetails", {})
    related_playlists = content_details.get("relatedPlaylists", {})
    playlist_id = related_playlists.get("uploads")

    if not playlist_id:
        logger.error("Uploads playlist missing in response for channel %s", channel_id)
        return None

    _uploads_playlist_cache[channel_id] = playlist_id
    global _uploads_cache_dirty
    _uploads_cache_dirty = True
    return playlist_id


def _is_ip_block_error(exception: Exception) -> bool:
    """Check if exception indicates IP blocking."""
    error_msg = str(exception).lower()
    ip_block_indicators = [
        "requestblocked",
        "ipblocked",
        "ip blocked",
        "too many requests",
        "429",
        "rate limit",
        "quota exceeded",
    ]
    return any(indicator in error_msg for indicator in ip_block_indicators)


def _activate_fallback_only_mode() -> None:
    """Activate fallback-only mode for remaining videos."""
    global _fallback_only_mode
    if not _fallback_only_mode:
        _fallback_only_mode = True
        logger.warning(
            "⚠️ Detected IP block/consecutive failures. "
            "Switching to audio fallback for remaining videos."
        )


def _reset_failure_counter() -> None:
    """Reset consecutive failure counter after successful extraction."""
    global _consecutive_failures
    _consecutive_failures = 0


def _increment_failure_counter() -> None:
    """Increment failure counter and check threshold."""
    global _consecutive_failures
    _consecutive_failures += 1

    if _consecutive_failures >= _CONSECUTIVE_FAILURES_THRESHOLD:
        logger.warning(
            f"Reached {_consecutive_failures} consecutive failures "
            f"(threshold: {_CONSECUTIVE_FAILURES_THRESHOLD})"
        )
        _activate_fallback_only_mode()


def _try_audio_fallback(
    video_url: str, video_id: Optional[str], language_code: str
) -> Optional[str]:
    """Attempt audio fallback if enabled."""
    if not is_fallback_enabled():
        logger.debug("Audio fallback is disabled via ENABLE_AUDIO_FALLBACK")
        return None

    logger.info(f"Attempting audio fallback for {video_url}")
    try:
        transcript = extract_transcript_via_audio(video_url, language_code)
        if transcript:
            _reset_failure_counter()
            return transcript
        else:
            logger.error("Audio fallback returned no transcript")
            return None
    except Exception as fallback_error:
        error_msg = str(fallback_error).lower()
        
        # Check if it's a live stream error - don't add to index so it can be retried later
        if "live" in error_msg or "upcoming" in error_msg:
            logger.warning(f"Video is live or upcoming, skipping for now (will retry on next run): {fallback_error}")
        else:
            logger.error(f"Audio fallback failed: {str(fallback_error)}")
            if video_id:
                try:
                    update_video_index(video_id, "AUDIO_FALLBACK_FAILED", False)
                except Exception as index_error:
                    logger.error(f"Failed to update video index: {str(index_error)}")
        return None


def get_youtube_transcript(
    video_url: str, language_code: str = "en", prefer_auto_generated: bool = False
) -> Optional[str]:
    """
    Extract transcript from a YouTube video and return it as a string.
    Uses youtube-transcript-api as primary method with audio fallback (yt-dlp + Whisper).

    Args:
        video_url (str): YouTube video URL
        language_code (str): Language code for the transcript (default: 'en' for English)
        prefer_auto_generated (bool): If True, prefer auto-generated transcripts over manual ones (default: False)

    Returns:
        str: Video transcript as a single string or None if transcript is not available
    """
    global _fallback_only_mode

    # Initialize video_id to None to ensure it's defined even if an exception occurs
    video_id = None

    # Extract video ID from URL first
    video_id = extract_video_id(url=video_url)
    if not video_id:
        logger.error(f"Failed to extract video ID from URL: {video_url}")
        return None

    # If in fallback-only mode, skip youtube-transcript-api entirely
    if _fallback_only_mode:
        logger.info(f"Fallback-only mode active. Using audio extraction for {video_id}")
        return _try_audio_fallback(video_url, video_id, language_code)

    max_retries = 10
    delay_seconds = 20

    for attempt in range(1, max_retries + 1):
        try:
            logger.debug(
                f"Extracting transcript for video ID: {video_id} with language: {language_code} (attempt {attempt})"
            )

            # Get transcript with specified language
            ytt_api = YouTubeTranscriptApi()

            if prefer_auto_generated:
                # Try to get auto-generated transcript first
                logger.debug(
                    f"Attempting to fetch auto-generated transcript for language: {language_code}"
                )
                transcript_list = ytt_api.list(video_id)  # type: ignore
                try:
                    transcript_obj = transcript_list.find_generated_transcript(
                        [language_code]
                    )  # type: ignore
                    transcript_fetched = transcript_obj.fetch()  # type: ignore
                    # Convert FetchedTranscriptSnippet objects to dict format
                    transcript_raw = [
                        {
                            "text": segment.text,
                            "start": segment.start,
                            "duration": segment.duration,
                        }  # type: ignore
                        for segment in transcript_fetched  # type: ignore
                    ]
                except Exception:
                    # Fallback to any available transcript in the language
                    logger.debug(
                        "No auto-generated transcript found, falling back to any available transcript"
                    )
                    transcript_raw = ytt_api.fetch(  # type: ignore
                        video_id, languages=[language_code]
                    ).to_raw_data()
            else:
                # Use the default behavior - prefer manual transcripts
                transcript_raw = ytt_api.fetch(  # type: ignore
                    video_id, languages=[language_code]
                ).to_raw_data()

            logger.debug(f"Retrieved {len(transcript_raw)} transcript segments")  # type: ignore

            # Combine all transcript pieces into one string
            transcript = " ".join(
                [segment["text"] for segment in transcript_raw]  # type: ignore
            )

            logger.debug(f"Transcript assembled with {len(transcript.split())} words")

            # Success! Reset failure counter
            _reset_failure_counter()
            return transcript

        except VideoUnavailable:
            logger.error(f"Video {video_url} is unavailable (attempt {attempt})")
            _increment_failure_counter()

            # Try audio fallback
            fallback_result = _try_audio_fallback(video_url, video_id, language_code)
            if fallback_result:
                return fallback_result

            # Fallback failed, update index
            if video_id:
                try:
                    update_video_index(video_id, "VIDEO_UNAVAILABLE", False)
                except Exception as index_error:
                    logger.error(f"Failed to update video index: {str(index_error)}")
            return None

        except TranslationLanguageNotAvailable:
            logger.warning(
                f"No transcript found for {video_url} in language '{language_code}' (attempt {attempt})"
            )
            _increment_failure_counter()

            # Try audio fallback
            fallback_result = _try_audio_fallback(video_url, video_id, language_code)
            if fallback_result:
                return fallback_result

            return None

        except TranscriptsDisabled:
            logger.warning(
                f"Transcripts are disabled for video {video_url} (attempt {attempt})"
            )
            _increment_failure_counter()

            # Try audio fallback
            fallback_result = _try_audio_fallback(video_url, video_id, language_code)
            if fallback_result:
                if video_id:
                    try:
                        update_video_index(
                            video_id, "TRANSCRIPTS_DISABLED_FALLBACK_SUCCEEDED", False
                        )
                    except Exception as index_error:
                        logger.error(
                            f"Failed to update video index: {str(index_error)}"
                        )
                return fallback_result

            # Fallback failed, update index
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
            logger.warning(
                f"No transcripts available for video {video_url} (attempt {attempt})"
            )
            _increment_failure_counter()

            # Try audio fallback
            fallback_result = _try_audio_fallback(video_url, video_id, language_code)
            if fallback_result:
                if video_id:
                    try:
                        update_video_index(
                            video_id, "NO_TRANSCRIPT_FOUND_FALLBACK_SUCCEEDED", False
                        )
                    except Exception as index_error:
                        logger.error(
                            f"Failed to update video index: {str(index_error)}"
                        )
                return fallback_result

            # Fallback failed, update index
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
            # Check for IP blocking
            if _is_ip_block_error(e):
                logger.error(f"IP block detected for {video_url}: {str(e)}")
                _activate_fallback_only_mode()

                if video_id:
                    try:
                        update_video_index(video_id, "IP_BLOCKED", False)
                    except Exception as index_error:
                        logger.error(
                            f"Failed to update video index: {str(index_error)}"
                        )

                # Try audio fallback immediately (no retry for IP blocks)
                return _try_audio_fallback(video_url, video_id, language_code)

            # Check for VideoUnplayable error message pattern
            if "The video is unplayable for the following reason:" in str(e):
                reason = (
                    str(e)
                    .split("The video is unplayable for the following reason:")[1]
                    .split("\n")[1]
                    .strip()
                )
                logger.warning(
                    f"Video unplayable for {video_url}: {reason} (attempt {attempt})"
                )
                _increment_failure_counter()

                # Try audio fallback
                fallback_result = _try_audio_fallback(
                    video_url, video_id, language_code
                )
                if fallback_result:
                    return fallback_result

                if video_id and not reason.strip():
                    try:
                        update_video_index(video_id, "VIDEO_UNPLAYABLE", False)
                    except Exception as index_error:
                        logger.error(
                            f"Failed to update video index: {str(index_error)}"
                        )
                return None

            # Handle other exceptions with retry
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
                _increment_failure_counter()

                # Try audio fallback as last resort
                return _try_audio_fallback(video_url, video_id, language_code)


def get_videos_from_channel(
    channel_id: str,
    days: int = 8,
    skip_verification: bool = False,
    max_pages: int = 100,  # Default to a high number to keep paginating
    max_videos: int = 10,
    skip_shorts: bool = False,
    shorts_max_duration_seconds: int = 120,
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
        skip_shorts (bool): If True, skip videos classified as YouTube Shorts
        shorts_max_duration_seconds (int): Duration threshold in seconds to classify videos as Shorts

    Returns:
        list[tuple[str, str, str]]: A list of tuples containing (video_url, video_title, published_date) for each video
    """
    API_KEY = os.getenv("YOUTUBE_API_KEY")
    if not API_KEY:
        logger.error(
            "YOUTUBE_API_KEY is not set. Skipping fetch for channel %s", channel_id
        )
        return []

    logger.debug(
        "Fetching videos from channel ID: %s for last %d days (max %d videos)",
        channel_id,
        days,
        max_videos,
    )

    processed_video_ids = get_processed_video_ids(skip_verification)
    logger.debug("Found %d already processed videos", len(processed_video_ids))

    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).replace(
        tzinfo=None
    )

    playlist_id = _get_uploads_playlist_id(channel_id, API_KEY)
    videos: list[tuple[str, str, str]] = []
    api_calls_count = 0

    if playlist_id:
        videos, api_calls_count = _collect_videos_from_playlist(
            playlist_id=playlist_id,
            api_key=API_KEY,
            processed_video_ids=processed_video_ids,
            skip_verification=skip_verification,
            skip_shorts=skip_shorts,
            shorts_max_duration_seconds=shorts_max_duration_seconds,
            max_pages=max_pages,
            max_videos=max_videos,
            channel_id=channel_id,
            start_date=start_date,
        )
    else:
        logger.warning(
            "Falling back to search API for channel %s due to missing playlist id",
            channel_id,
        )
        videos, api_calls_count = _collect_videos_via_search(
            channel_id=channel_id,
            api_key=API_KEY,
            processed_video_ids=processed_video_ids,
            skip_verification=skip_verification,
            skip_shorts=skip_shorts,
            shorts_max_duration_seconds=shorts_max_duration_seconds,
            max_pages=max_pages,
            max_videos=max_videos,
            start_date=start_date,
        )

    _save_uploads_playlist_cache()

    logger.debug(
        "Made %d API calls for channel %s, collected %d videos",
        api_calls_count,
        channel_id,
        len(videos),
    )
    return videos


def _collect_videos_from_playlist(
    *,
    playlist_id: str,
    api_key: str,
    processed_video_ids: set[str],
    skip_verification: bool,
    skip_shorts: bool,
    shorts_max_duration_seconds: int,
    max_pages: int,
    max_videos: int,
    channel_id: str,
    start_date: datetime,
) -> tuple[list[tuple[str, str, str]], int]:
    videos: list[tuple[str, str, str]] = []
    page_token: Optional[str] = None
    page_count = 0
    api_calls_count = 0

    while page_count < max_pages and len(videos) < max_videos:
        page_count += 1
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": "50",
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token

        logger.debug(
            "Fetching playlistItems page %d for channel %s (playlist %s)",
            page_count,
            channel_id,
            playlist_id,
        )

        try:
            data = _request_json(f"{_YOUTUBE_API_BASE}/playlistItems", params)
            api_calls_count += 1
        except requests.HTTPError as http_exc:
            message = _extract_youtube_error_message(http_exc)
            logger.error(
                "YouTube API error (playlistItems) for channel %s: %s",
                channel_id,
                message,
            )
            break
        except (
            Exception
        ) as exc:  # pragma: no cover - network errors are rare/hard to mock
            logger.error(
                "Unexpected error fetching playlistItems for channel %s: %s",
                channel_id,
                str(exc),
                exc_info=True,
            )
            break

        items = data.get("items") or []
        if not items:
            logger.debug("No items returned for playlist %s", playlist_id)
            break

        staged_items: list[dict[str, str]] = []
        video_ids_for_duration: list[str] = []
        all_items_older_than_window = True

        for item in items:
            content_details = item.get("contentDetails", {})
            snippet = item.get("snippet", {})
            video_id = content_details.get("videoId")
            title = snippet.get("title") or "(untitled video)"
            published_at_raw = content_details.get("videoPublishedAt") or snippet.get(
                "publishedAt"
            )

            if not video_id or not published_at_raw:
                logger.debug(
                    "Skipping playlist item missing videoId or publishedAt for channel %s",
                    channel_id,
                )
                continue

            try:
                published_at_dt = datetime.fromisoformat(
                    published_at_raw.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except ValueError:
                logger.debug(
                    "Could not parse publishedAt '%s' for video %s",
                    published_at_raw,
                    video_id,
                )
                continue

            if published_at_dt < start_date:
                logger.debug(
                    "Skipping video %s from %s (before window)",
                    video_id,
                    published_at_dt,
                )
                continue

            all_items_older_than_window = False

            if not skip_verification and video_id in processed_video_ids:
                logger.debug("Video %s already processed. Skipping...", video_id)
                continue

            published_date = published_at_dt.date().isoformat()
            staged_items.append(
                {
                    "video_id": video_id,
                    "title": title,
                    "published_date": published_date,
                }
            )

            if skip_shorts:
                video_ids_for_duration.append(video_id)

        durations: dict[str, Optional[int]] = {}
        if skip_shorts and video_ids_for_duration:
            durations = _fetch_video_durations(video_ids_for_duration, api_key)

        for staged in staged_items:
            if len(videos) >= max_videos:
                logger.info(
                    "Reached maximum videos limit (%d) for channel %s",
                    max_videos,
                    channel_id,
                )
                break

            video_id = staged["video_id"]
            if skip_shorts:
                duration_seconds = durations.get(video_id)
                if (
                    duration_seconds is not None
                    and duration_seconds <= shorts_max_duration_seconds
                ):
                    logger.debug(
                        "Skipping short video '%s' (%ss) from channel %s",
                        staged["title"],
                        duration_seconds,
                        channel_id,
                    )
                    continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            videos.append((video_url, staged["title"], staged["published_date"]))

        if len(videos) >= max_videos:
            break

        page_token = data.get("nextPageToken")
        if not page_token:
            logger.debug("No additional playlist pages for channel %s", channel_id)
            break

        if all_items_older_than_window:
            logger.debug(
                "All items on page %d for channel %s were older than window; stopping",
                page_count,
                channel_id,
            )
            break

    return videos, api_calls_count


def _collect_videos_via_search(
    *,
    channel_id: str,
    api_key: str,
    processed_video_ids: set[str],
    skip_verification: bool,
    skip_shorts: bool,
    shorts_max_duration_seconds: int,
    max_pages: int,
    max_videos: int,
    start_date: datetime,
) -> tuple[list[tuple[str, str, str]], int]:
    videos: list[tuple[str, str, str]] = []
    page_token: Optional[str] = None
    page_count = 0
    api_calls_count = 0

    published_after = start_date.isoformat(timespec="seconds") + "Z"

    while page_count < max_pages and len(videos) < max_videos:
        page_count += 1
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "date",
            "publishedAfter": published_after,
            "key": api_key,
            "maxResults": "50",
        }
        if page_token:
            params["pageToken"] = page_token

        try:
            data = _request_json(f"{_YOUTUBE_API_BASE}/search", params)
            api_calls_count += 1
        except requests.HTTPError as http_exc:
            message = _extract_youtube_error_message(http_exc)
            logger.error(
                "YouTube API error (search) for channel %s: %s",
                channel_id,
                message,
            )
            break
        except (
            Exception
        ) as exc:  # pragma: no cover - network errors are rare/hard to mock
            logger.error(
                "Unexpected error fetching search results for channel %s: %s",
                channel_id,
                str(exc),
                exc_info=True,
            )
            break

        if "error" in data:
            logger.error(
                "YouTube API error payload (search) for channel %s: %s",
                channel_id,
                data["error"].get("message", "Unknown error"),
            )
            break

        items = data.get("items") or []
        if not items:
            logger.debug("No items returned from search for channel %s", channel_id)
            break

        video_ids_for_duration: list[str] = []
        durations: dict[str, Optional[int]] = {}

        if skip_shorts:
            video_ids_for_duration = [
                item.get("id", {}).get("videoId")
                for item in items
                if isinstance(item.get("id"), dict)
                and item.get("id", {}).get("videoId")
            ]
            if video_ids_for_duration:
                durations = _fetch_video_durations(video_ids_for_duration, api_key)

        for item in items:
            if len(videos) >= max_videos:
                logger.info(
                    "Reached maximum videos limit (%d) for channel %s",
                    max_videos,
                    channel_id,
                )
                break

            video_id = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            title = snippet.get("title") or "(untitled video)"
            published_at = snippet.get("publishedAt")

            if not video_id or not published_at:
                logger.debug(
                    "Skipping search item missing videoId or publishedAt for channel %s",
                    channel_id,
                )
                continue

            try:
                published_at_dt = datetime.fromisoformat(
                    published_at.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except ValueError:
                logger.debug(
                    "Could not parse search publishedAt '%s' for video %s",
                    published_at,
                    video_id,
                )
                continue

            if published_at_dt < start_date:
                logger.debug(
                    "Skipping search result %s from %s (before window)",
                    video_id,
                    published_at_dt,
                )
                continue

            if not skip_verification and video_id in processed_video_ids:
                logger.debug(
                    "Search result %s already processed. Skipping...", video_id
                )
                continue

            if skip_shorts:
                duration_seconds = durations.get(video_id)
                if (
                    duration_seconds is not None
                    and duration_seconds <= shorts_max_duration_seconds
                ):
                    logger.debug(
                        "Skipping short search result '%s' (%ss) from channel %s",
                        title,
                        duration_seconds,
                        channel_id,
                    )
                    continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            videos.append((video_url, title, published_at_dt.date().isoformat()))

        if len(videos) >= max_videos:
            break

        page_token = data.get("nextPageToken")
        if not page_token:
            logger.debug("No additional search pages for channel %s", channel_id)
            break

    return videos, api_calls_count


def _parse_iso8601_duration(duration: Optional[str]) -> Optional[int]:
    """Convert an ISO 8601 duration string (e.g. PT5M30S) to seconds."""
    if not duration:
        return None

    match = _DURATION_PATTERN.fullmatch(duration)
    if not match:
        logger.debug(f"Failed to parse ISO 8601 duration: {duration}")
        return None

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)

    return hours * 3600 + minutes * 60 + seconds


def _fetch_video_durations(
    video_ids: list[str], api_key: Optional[str]
) -> dict[str, Optional[int]]:
    """Fetch the duration (in seconds) for the provided YouTube video IDs."""
    if not video_ids:
        return {}

    if not api_key:
        logger.warning(
            "YOUTUBE_API_KEY not set; cannot filter YouTube Shorts by duration."
        )
        return {vid: None for vid in video_ids}

    base_url = "https://www.googleapis.com/youtube/v3/videos"
    durations: dict[str, Optional[int]] = {}

    for start in range(0, len(video_ids), 50):
        chunk = video_ids[start : start + 50]
        params = {
            "part": "contentDetails",
            "id": ",".join(chunk),
            "key": api_key,
        }

        try:
            response = requests.get(base_url, params=params)
            data = response.json()

            if "error" in data:
                logger.error(
                    "YouTube API error fetching durations: %s",
                    data["error"].get("message", "Unknown error"),
                )
                continue

            for item in data.get("items", []):
                vid = item.get("id")
                content_details = item.get("contentDetails", {})
                duration_str = content_details.get("duration")
                if vid:
                    durations[vid] = _parse_iso8601_duration(duration_str)

        except (
            Exception
        ) as exc:  # pragma: no cover - network errors are rare/hard to mock
            logger.error(f"Error fetching video durations: {str(exc)}")
            break

    for vid in video_ids:
        durations.setdefault(vid, None)

    return durations


def extract_video_id(url: str) -> Optional[str]:
    # Extract video ID from different YouTube URL formats
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    return None


def get_video_details_from_url(
    url: str,
    skip_verification: bool = False,
    include_processed: bool = False,
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
    if video_id in processed_video_ids and not include_processed:
        logger.debug(
            f"Video with ID {video_id} was already processed. Skipping... (include_processed=False)"
        )
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
