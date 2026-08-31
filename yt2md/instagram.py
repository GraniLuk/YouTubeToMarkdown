"""Module for collecting and processing Instagram reels and posts."""

import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from yt2md.audio_fallback import (
    _get_ytdlp_auth_opts,
    _get_ytdlp_base_opts,
    extract_transcript_via_audio,
)
from yt2md.file_operations import sanitize_filename
from yt2md.logger import get_logger
from yt2md.video_index import get_processed_video_ids

logger = get_logger("instagram")

_INSTAGRAM_URL_PATTERN = re.compile(
    r"(?:https?:\/\/)?(?:www\.)?(?:instagram\.com|instagr\.am)\/(?:[a-zA-Z0-9_\.]+\/)?(?:reel|reels|p|tv)\/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
_INSTAGRAM_PROFILE_PATTERN = re.compile(
    r"(?:https?:\/\/)?(?:www\.)?(?:instagram\.com|instagr\.am)\/([a-zA-Z0-9_\.]+)",
    re.IGNORECASE,
)


def is_instagram_url(url: str) -> bool:
    """Check if the provided URL or ID belongs to Instagram."""
    if not url:
        return False
    url_lower = url.strip().lower()
    return "instagram.com" in url_lower or "instagr.am" in url_lower


def extract_instagram_id(url: str) -> Optional[str]:
    """Extract Instagram post/reel shortcode/ID from a URL or raw ID string."""
    if not url:
        return None
    url = url.strip()
    match = _INSTAGRAM_URL_PATTERN.search(url)
    if match:
        return match.group(1)
    # If already a simple ID/shortcode without URL parts
    if re.match(r"^[a-zA-Z0-9_-]{5,20}$", url) and not url.startswith("http"):
        return url
    return None


def clean_instagram_username(profile_id_or_url: str) -> str:
    """Extract clean username from URL, @username, or profile ID."""
    raw = profile_id_or_url.strip()
    if raw.startswith("@"):
        raw = raw[1:]
    raw = raw.split("?")[0].split("#")[0]
    parts = [
        p
        for p in raw.split("/")
        if p
        and p.lower()
        not in (
            "https:",
            "http:",
            "www.instagram.com",
            "instagram.com",
            "instagr.am",
            "reel",
            "reels",
            "p",
            "tv",
            "stories",
            "explore",
        )
    ]
    if parts:
        return parts[0].strip()
    return raw.strip("/").split("/")[-1]


def get_instagram_profile_url(profile_id_or_url: str) -> str:
    """Return standard Instagram profile URL for yt-dlp."""
    username = clean_instagram_username(profile_id_or_url)
    return f"https://www.instagram.com/{username}/"


def _clean_title_from_post(entry: Dict[str, Any], default_title: str) -> str:
    """Extract a descriptive and readable title from post metadata or description."""
    title = entry.get("title") or ""
    description = entry.get("description") or ""

    # Check if title is generic (e.g. 'Instagram post #DF2HwPvo1U5' or just username)
    is_generic = (
        not title
        or "Instagram post" in title
        or title == entry.get("uploader")
        or title == entry.get("id")
    )

    if is_generic and description:
        # Use first non-empty line of description as title
        first_line = description.strip().split("\n")[0].strip()
        # Remove markdown/hashtags at start
        first_line = re.sub(r"^#+\s*", "", first_line).strip()
        if len(first_line) > 100:
            first_line = first_line[:97] + "..."
        if len(first_line) > 3:
            return first_line

    if title and not is_generic:
        return title

    return default_title


def _parse_entry_date(entry: Dict[str, Any]) -> Optional[datetime]:
    """Extract publication datetime from a yt-dlp entry."""
    timestamp = entry.get("timestamp")
    if timestamp:
        try:
            return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            pass

    upload_date = entry.get("upload_date")
    if upload_date and len(upload_date) == 8:
        try:
            return datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def _extract_cookies_dict_from_file(cookie_file: Optional[str]) -> Dict[str, str]:
    """Parse cookie file (Netscape or key=value or raw sessionid) into a dictionary."""
    cookies: Dict[str, str] = {}
    if not cookie_file or not os.path.exists(cookie_file):
        return cookies

    try:
        with open(cookie_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if content.startswith("# Netscape") or "\t" in content:
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    name = parts[5].strip()
                    val = parts[6].strip()
                    cookies[name] = val
        else:
            raw = content.strip()
            if "sessionid=" in raw:
                for item in raw.split(";"):
                    item = item.strip()
                    if "=" in item:
                        k, v = item.split("=", 1)
                        cookies[k.strip()] = v.strip()
            elif len(raw) > 10:
                cookies["sessionid"] = raw
                if "%3A" in raw or ":" in raw:
                    user_id = raw.split("%3A")[0].split(":")[0]
                    cookies["ds_user_id"] = user_id
    except Exception as e:
        logger.debug(f"Error parsing cookies file {cookie_file}: {e}")

    return cookies


def _get_reels_from_profile_instaloader(
    username: str,
    days: int = 3,
    max_videos: int = 10,
    skip_verification: bool = False,
    channel_name: Optional[str] = None,
    title_filters: Optional[List[str]] = None,
    cookie_file: Optional[str] = None,
) -> List[Tuple[str, str, str, str]]:
    """Fallback method using instaloader to fetch reels from an Instagram profile."""
    try:
        import instaloader
    except ImportError:
        logger.debug("instaloader not installed, skipping instaloader fallback")
        return []

    cookies = _extract_cookies_dict_from_file(cookie_file)
    if not cookies:
        return []

    try:
        logger.info(f"📸 Próba pobrania rolek przez Instaloader dla @{username}...")
        L = instaloader.Instaloader(sleep=False, max_connection_attempts=1, quiet=True)
        for k, v in cookies.items():
            L.context._session.cookies.set(k, v, domain=".instagram.com")

        L.context._session.headers.update(
            {
                "X-IG-App-ID": "936619743392459",
                "X-ASBD-ID": "129477",
                "X-Instagram-AJAX": "1",
                "Referer": "https://www.instagram.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            }
        )

        profile = instaloader.Profile.from_username(L.context, username)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        processed_ids = get_processed_video_ids(skip_verification)
        collected: List[Tuple[str, str, str, str]] = []
        display_name = channel_name or profile.full_name or username

        for post in profile.get_posts():
            if not post.is_video:
                continue

            post_id = post.shortcode
            if post_id in processed_ids:
                continue

            post_dt = (
                post.date_utc.replace(tzinfo=timezone.utc)
                if post.date_utc.tzinfo is None
                else post.date_utc
            )
            if post_dt < cutoff_date:
                break

            pub_date_str = post_dt.strftime("%Y-%m-%d")
            reel_url = f"https://www.instagram.com/reel/{post_id}/"

            caption = post.caption or ""
            first_line = caption.strip().split("\n")[0].strip() if caption else ""
            first_line = re.sub(r"^#+\s*", "", first_line).strip()
            title = first_line[:100] if len(first_line) > 3 else f"Instagram Reel #{post_id}"

            if title_filters:
                combined_text = f"{title} {caption}".lower()
                if not any(f.lower() in combined_text for f in title_filters):
                    continue

            collected.append((reel_url, title, pub_date_str, display_name))
            if len(collected) >= max_videos:
                break

        logger.info(f"Zebrano {len(collected)} nowych rolek przez Instaloader dla @{username}")
        return collected
    except Exception as exc:
        logger.debug(f"Instaloader profile fetch failed: {exc}")
        return []


def _get_reels_from_profile_web_api(
    username: str,
    days: int = 3,
    max_videos: int = 10,
    skip_verification: bool = False,
    channel_name: Optional[str] = None,
    title_filters: Optional[List[str]] = None,
    cookie_file: Optional[str] = None,
) -> Optional[List[Tuple[str, str, str, str]]]:
    """
    Fetch profile reels directly from Instagram Web Feed API using cookies.
    Returns list of reels on success (can be empty if none found / all processed),
    or None if the API request itself fails.
    """
    import requests

    cookies = _extract_cookies_dict_from_file(cookie_file)
    if not cookies:
        return None

    session = requests.Session()
    for k, v in cookies.items():
        session.cookies.set(k, v, domain=".instagram.com")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "X-IG-App-ID": "936619743392459",
        "X-CSRFToken": cookies.get("csrftoken", ""),
        "X-ASBD-ID": "129477",
        "Referer": f"https://www.instagram.com/{username}/",
    }

    try:
        # 1. Resolve user PK
        user_pk = None
        display_name = channel_name or username
        search_url = f"https://www.instagram.com/api/v1/web/search/topsearch/?context=blended&query={username}"
        s_resp = session.get(search_url, headers=headers, timeout=15)
        if s_resp.status_code == 200:
            for u in s_resp.json().get("users", []):
                u_obj = u.get("user", {})
                if u_obj.get("username", "").lower() == username.lower():
                    user_pk = u_obj.get("pk")
                    if not channel_name:
                        display_name = u_obj.get("full_name") or username
                    break

        if not user_pk:
            logger.debug(f"Could not resolve user PK for @{username}")
            return None

        # 2. Query user feed with pagination support
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        processed_ids = get_processed_video_ids(skip_verification)
        collected: List[Tuple[str, str, str, str]] = []
        max_id = None
        has_more = True

        while has_more and len(collected) < max_videos:
            feed_url = f"https://www.instagram.com/api/v1/feed/user/{user_pk}/"
            if max_id:
                feed_url += f"?max_id={max_id}"

            feed_resp = session.get(feed_url, headers=headers, timeout=15)
            if feed_resp.status_code != 200:
                logger.debug(f"Feed request returned status {feed_resp.status_code}")
                # If we already collected some items, return them, else None
                return collected if collected else None

            feed_json = feed_resp.json()
            items = feed_json.get("items", [])
            if not items:
                break

            reached_cutoff = False
            for it in items:
                code = it.get("code")
                if not code:
                    continue

                is_pinned = bool(it.get("timeline_pinned_user_ids") or it.get("is_pinned"))
                media_type = it.get("media_type")
                is_video = media_type == 2 or bool(it.get("video_versions"))
                if not is_video:
                    continue

                taken_at = it.get("taken_at")
                if taken_at:
                    dt = datetime.fromtimestamp(taken_at, tz=timezone.utc)
                    if dt < cutoff_date:
                        # Pinned posts can have ancient dates at top of profile - do not abort pagination on them
                        if not is_pinned:
                            reached_cutoff = True
                        continue
                    pub_date_str = dt.strftime("%Y-%m-%d")
                else:
                    pub_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                if code in processed_ids:
                    logger.debug(f"Pominięto już przetworzoną rolkę ID: {code}")
                    continue

                reel_url = f"https://www.instagram.com/reel/{code}/"

                caption_obj = it.get("caption") or {}
                caption_text = (
                    caption_obj.get("text", "")
                    if isinstance(caption_obj, dict)
                    else str(caption_obj)
                )
                first_line = caption_text.strip().split("\n")[0].strip() if caption_text else ""
                first_line = re.sub(r"^#+\s*", "", first_line).strip()
                title = first_line[:100] if len(first_line) > 3 else f"Instagram Reel #{code}"

                if title_filters:
                    combined_text = f"{title} {caption_text}".lower()
                    if not any(f.lower() in combined_text for f in title_filters):
                        continue

                collected.append((reel_url, title, pub_date_str, display_name))
                if len(collected) >= max_videos:
                    break

            if reached_cutoff or not feed_json.get("more_available"):
                break
            max_id = feed_json.get("next_max_id")
            if not max_id:
                break

        logger.info(f"Zebrano {len(collected)} nowych rolek dla @{username}")
        return collected
    except Exception as exc:
        logger.debug(f"Instagram Web API fetch error: {exc}")
        return None


def get_reels_from_profile(
    profile_id_or_url: str,
    days: int = 3,
    max_videos: int = 10,
    skip_verification: bool = False,
    channel_name: Optional[str] = None,
    title_filters: Optional[List[str]] = None,
) -> List[Tuple[str, str, str, str]]:
    """
    Collect reels from an Instagram profile published within the last `days` days.

    Args:
        profile_id_or_url: Instagram profile username or URL
        days: Lookback window in days
        max_videos: Maximum number of reels to collect
        skip_verification: If True, ignore processed video index
        channel_name: Human-friendly channel name override
        title_filters: Optional list of keyword filters for title/description

    Returns:
        List of tuples: (video_url, title, published_date_str, uploader)
    """
    username = clean_instagram_username(profile_id_or_url)
    profile_url = get_instagram_profile_url(profile_id_or_url)
    display_name = channel_name or username

    logger.info(f"📸 Pobieranie rolek dla profilu Instagram: @{username} ({profile_url})")

    auth_opts = _get_ytdlp_auth_opts("instagram")
    base_opts = _get_ytdlp_base_opts()
    cookie_file = auth_opts.get("cookiefile")

    # Strategy 1: Direct Instagram Web Feed API (most reliable with session cookies)
    reels_api = _get_reels_from_profile_web_api(
        username=username,
        days=days,
        max_videos=max_videos,
        skip_verification=skip_verification,
        channel_name=display_name,
        title_filters=title_filters,
        cookie_file=cookie_file,
    )
    if reels_api is not None:
        return reels_api

    # Strategy 2: yt-dlp profile extractor
    try:
        import yt_dlp
        ydl_opts = {
            **base_opts,
            **auth_opts,
            "extract_flat": "in_playlist",
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(profile_url, download=False)
            if info and info.get("entries"):
                raw_entries = list(info.get("entries"))
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
                processed_ids = get_processed_video_ids(skip_verification)
                collected: List[Tuple[str, str, str, str]] = []
                for entry in raw_entries:
                    if not entry:
                        continue
                    post_id = entry.get("id") or extract_instagram_id(entry.get("url", ""))
                    if not post_id or post_id in processed_ids:
                        continue
                    pub_dt = _parse_entry_date(entry)
                    if pub_dt:
                        if pub_dt < cutoff_date:
                            continue
                        pub_date_str = pub_dt.strftime("%Y-%m-%d")
                    else:
                        pub_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    reel_url = f"https://www.instagram.com/reel/{post_id}/"
                    title = _clean_title_from_post(entry, f"Instagram Reel #{post_id}")
                    if title_filters:
                        desc = entry.get("description") or ""
                        if not any(f.lower() in f"{title} {desc}".lower() for f in title_filters):
                            continue
                    uploader = display_name or entry.get("uploader") or username
                    collected.append((reel_url, title, pub_date_str, uploader))
                    if len(collected) >= max_videos:
                        break
                if collected:
                    return collected
    except Exception as exc:
        logger.debug(f"yt-dlp profile fetch failed: {exc}")

    # Strategy 3: Instaloader fallback
    reels_il = _get_reels_from_profile_instaloader(
        username=username,
        days=days,
        max_videos=max_videos,
        skip_verification=skip_verification,
        channel_name=display_name,
        title_filters=title_filters,
        cookie_file=cookie_file,
    )
    if reels_il:
        return reels_il

    logger.warning(
        f"Nie udało się pobrać rolek z {profile_url}. "
        "Upewnij się, że plik cookies.txt lub cookies_instagram.txt zawiera poprawne ciasteczka Instagrama."
    )
    return []

    raw_entries = info.get("entries") or []
    if not isinstance(raw_entries, list):
        raw_entries = list(raw_entries)

    logger.debug(f"Znaleziono {len(raw_entries)} wpisów na profilu @{username}")

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    processed_ids = get_processed_video_ids(skip_verification)

    collected_reels: List[Tuple[str, str, str, str]] = []

    for entry in raw_entries:
        if not entry:
            continue

        entry_url = entry.get("url") or ""
        post_id = entry.get("id") or extract_instagram_id(entry_url)
        if not post_id:
            continue

        # Skip already processed videos
        if post_id in processed_ids:
            logger.debug(f"Pominięto już przetworzoną rolkę ID: {post_id}")
            continue

        # Check date filter
        pub_dt = _parse_entry_date(entry)
        if pub_dt:
            if pub_dt < cutoff_date:
                logger.debug(
                    f"Pominięto rolkę {post_id} z daty {pub_dt.strftime('%Y-%m-%d')} (starsza niż {days} dni)"
                )
                continue
            pub_date_str = pub_dt.strftime("%Y-%m-%d")
        else:
            pub_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Canonical reel URL
        reel_url = f"https://www.instagram.com/reel/{post_id}/"

        # Determine title
        default_title = f"Instagram Reel #{post_id}"
        title = _clean_title_from_post(entry, default_title)

        # Title / description filters
        if title_filters:
            desc = entry.get("description") or ""
            combined_text = f"{title} {desc}".lower()
            if not any(f.lower() in combined_text for f in title_filters):
                logger.debug(
                    f"Pominięto rolkę {post_id} - brak dopasowania do filtrów: {title_filters}"
                )
                continue

        uploader = display_name or entry.get("uploader") or username

        collected_reels.append((reel_url, title, pub_date_str, uploader))

        if len(collected_reels) >= max_videos:
            break

    logger.info(
        f"Zebrano {len(collected_reels)} nowych rolek z profilu @{username} z ostatnich {days} dni"
    )
    return collected_reels


def get_reel_details_from_url(
    url: str,
    skip_verification: bool = False,
) -> Optional[Tuple[str, str, str, str]]:
    """
    Fetch details for a single Instagram Reel/post.

    Args:
        url: Instagram URL
        skip_verification: If True, ignore processed index

    Returns:
        Tuple: (video_url, title, published_date, uploader) or None
    """
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt-dlp is required to process Instagram URLs.")
        return None

    post_id = extract_instagram_id(url)
    if not post_id:
        logger.error(f"Nieprawidłowy adres URL Instagrama: {url}")
        return None

    processed_ids = get_processed_video_ids(skip_verification)
    if post_id in processed_ids:
        logger.debug(f"Rolka z ID {post_id} została już przetworzona. Pomijanie.")
        return None

    canonical_url = f"https://www.instagram.com/reel/{post_id}/"
    auth_opts = _get_ytdlp_auth_opts("instagram")
    base_opts = _get_ytdlp_base_opts()

    ydl_opts = {
        **base_opts,
        **auth_opts,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(canonical_url, download=False)
    except Exception as exc:
        logger.error(f"Błąd pobierania danych rolki {canonical_url}: {exc}")
        return None

    if not info:
        return None

    pub_dt = _parse_entry_date(info)
    pub_date_str = (
        pub_dt.strftime("%Y-%m-%d")
        if pub_dt
        else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )

    uploader = info.get("uploader") or info.get("channel") or "Instagram"
    title = _clean_title_from_post(info, f"Instagram Reel #{post_id}")

    return (canonical_url, title, pub_date_str, uploader)


def get_instagram_post_caption(url: str) -> Optional[str]:
    """Retrieve the text caption/description of an Instagram post using yt-dlp."""
    try:
        import yt_dlp
        auth_opts = _get_ytdlp_auth_opts("instagram")
        base_opts = _get_ytdlp_base_opts()
        ydl_opts = {
            **base_opts,
            **auth_opts,
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return info.get("description") or None
    except Exception as e:
        logger.debug(f"Could not retrieve caption for {url}: {e}")
    return None


def get_instagram_transcript(
    video_url: str,
    language_code: str = "pl",
    prefer_auto_generated: bool = False,
) -> Optional[str]:
    """
    Extract transcript for an Instagram reel using yt-dlp audio download + Whisper,
    enriching the context with post caption if available.

    Args:
        video_url: Instagram Reel/Video URL
        language_code: Target language code for Whisper
        prefer_auto_generated: Kept for API consistency with YouTube extractor

    Returns:
        Combined transcript and post context string, or fallback string if extraction fails
    """
    logger.info(f"🎙️ Pobieranie transkrypcji audio dla rolki: {video_url}")

    audio_transcript = None
    # Step 1: Transcribe audio using Whisper audio fallback
    try:
        audio_transcript = extract_transcript_via_audio(
            video_url, language_code=language_code
        )
    except Exception as exc:
        logger.debug(f"Audio fallback extraction skipped/failed for {video_url}: {exc}")

    # Step 2: Fetch post caption/description
    post_caption = get_instagram_post_caption(video_url)

    if audio_transcript and post_caption:
        # Combine transcript with post caption context
        combined = (
            f"[Transkrypcja audio nagrania (Whisper)]:\n{audio_transcript}\n\n"
            f"[Opis posta / treść wpisu twórcy]:\n{post_caption}"
        )
        return combined
    elif audio_transcript:
        return audio_transcript
    elif post_caption:
        # Fallback to post caption if speech was not detected (e.g. background music only)
        logger.info(
            f"Brak transkrypcji audio dla {video_url}, użycie opisu posta jako treści"
        )
        return f"[Treść opisu posta]:\n{post_caption}"
    else:
        logger.info(
            f"Brak transkrypcji i opisu dla {video_url}, utworzenie notatki bazowej"
        )
        return f"Rolka Instagram bez transkrypcji audio i opisu. Obejrzyj nagranie: {video_url}"
