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


_GENERIC_TITLE_PREFIX_PATTERN = re.compile(
    r"^(?:video|post|reel|photo)\s+by\b|^instagram\s+(?:post|reel|video|photo)\b",
    re.IGNORECASE,
)

_SPONSOR_WORDS = {
    "reklama",
    "wspolpraca",
    "współpraca",
    "platna wspolpraca",
    "płatna współpraca",
    "ad",
    "sponsored",
    "paid partnership",
    "autopromocja",
}


def _extract_title_from_caption(
    caption: Optional[str], fallback_title: str = ""
) -> str:
    """
    Extract a clean, descriptive title from a post caption/description.
    Skips hashtag-only lines, advertisement/sponsorship notices, and trims to <= 100 chars.
    """
    if not caption:
        return fallback_title

    for raw_line in caption.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Strip markdown syntax, bullets, leading hashes, dashes, tildes, quotes
        cleaned = re.sub(r"^[#\s\-*•—–~\"'„”]+", "", line).strip()
        if not cleaned:
            continue

        # Check if the line consists solely of hashtags (e.g. "#fit #gym #food")
        tokens = line.split()
        if tokens and all(t.startswith("#") for t in tokens):
            continue

        # Check if line is a common sponsorship/ad disclaimer
        lower_cleaned = cleaned.lower()
        if lower_cleaned in _SPONSOR_WORDS or any(
            lower_cleaned.startswith(f"{w}:") or lower_cleaned.startswith(f"{w} -")
            for w in _SPONSOR_WORDS
        ):
            continue

        # Check if the line has actual alphanumeric content
        if not any(c.isalnum() for c in cleaned):
            continue

        # Strip trailing hashtag clutter (e.g. "Delicious meal #yummy #lunch" -> "Delicious meal")
        cleaned = re.sub(r"\s+#\w+.*$", "", cleaned).strip()

        # Truncate to 100 chars cleanly
        if len(cleaned) > 100:
            truncated = cleaned[:97]
            last_space = truncated.rfind(" ")
            if last_space > 60:
                cleaned = truncated[:last_space] + "..."
            else:
                cleaned = truncated + "..."

        if len(cleaned) > 3 and any(c.isalnum() for c in cleaned):
            return cleaned

    return fallback_title


def _clean_title_from_post(entry: Dict[str, Any], default_title: str) -> str:
    """Extract a descriptive and readable title from post metadata or description."""
    title = (entry.get("title") or "").strip()
    description = entry.get("description") or ""
    uploader = (entry.get("uploader") or entry.get("channel") or "").strip()
    post_id = str(entry.get("id") or "").strip()

    # Determine if title is generic
    is_generic = False
    if not title:
        is_generic = True
    elif _GENERIC_TITLE_PREFIX_PATTERN.search(title):
        is_generic = True
    elif "instagram post" in title.lower():
        is_generic = True
    elif uploader and title.lower() in (
        uploader.lower(),
        f"video by {uploader.lower()}",
        f"post by {uploader.lower()}",
        f"reel by {uploader.lower()}",
    ):
        is_generic = True
    elif post_id and (title == post_id or title == f"#{post_id}"):
        is_generic = True
    elif title.lower() in ("instagram", "video", "reel", "post", "untitled", "untitled content"):
        is_generic = True

    if is_generic:
        # Try extracting from description
        fallback = default_title or (f"Instagram Reel #{post_id}" if post_id else "Instagram Reel")
        extracted = _extract_title_from_caption(description)
        if extracted:
            return extracted
        return fallback

    return title


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
                    domain = parts[0].strip().lower()
                    if "instagram.com" not in domain and "instagr.am" not in domain:
                        continue
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
            title = _extract_title_from_caption(caption, f"Instagram Reel #{post_id}")

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
    min_days: int = 0,
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
        min_date = (
            datetime.now(timezone.utc) - timedelta(days=min_days)
            if min_days > 0
            else None
        )
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
                    if min_date and dt > min_date:
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
                title = _extract_title_from_caption(caption_text, f"Instagram Reel #{code}")

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


def _get_reels_from_profile_selenium(
    username: str,
    days: int = 3,
    max_videos: int = 10,
    skip_verification: bool = False,
    channel_name: Optional[str] = None,
    title_filters: Optional[List[str]] = None,
    cookie_file: Optional[str] = None,
    min_days: int = 0,
) -> Optional[List[Tuple[str, str, str, str]]]:
    """
    Fallback method using Selenium headless Chrome to fetch reel URLs from /{username}/reels/.
    Bypasses API 429 rate limits, broken yt-dlp profile extractors, and feedback_required errors.
    Returns list of reels on success (can be empty if none found / all processed),
    or None if Selenium failed or could not run.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
    except ImportError:
        logger.debug("selenium not installed, skipping selenium fallback")
        return None

    cookies = _extract_cookies_dict_from_file(cookie_file)
    if not cookies:
        logger.debug("No cookies available for Selenium Instagram fallback")
        return None

    logger.info(f"📸 Próba pobrania rolek przez Headless Chrome dla @{username}...")
    driver = None
    collected_urls: List[str] = []

    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--mute-audio")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        )

        driver = webdriver.Chrome(options=options)

        # First visit root to establish domain context for cookies
        try:
            driver.get("https://www.instagram.com/")
        except Exception:
            pass
        time.sleep(1.5)

        for k, v in cookies.items():
            try:
                driver.add_cookie(
                    {
                        "name": k,
                        "value": v,
                        "domain": ".instagram.com",
                        "path": "/",
                    }
                )
            except Exception:
                pass

        # Navigate to reels page
        reels_url = f"https://www.instagram.com/{username}/reels/"
        try:
            driver.get(reels_url)
        except Exception:
            pass
        time.sleep(3.0)

        # Scroll and collect reel links
        processed_ids = get_processed_video_ids(skip_verification)
        seen_codes = set()
        unprocessed_candidate_count = 0
        no_new_links_count = 0
        max_scrolls = max(25, int(days * 0.4))

        for scroll_i in range(max_scrolls):
            raw_hrefs = []
            try:
                raw_hrefs = driver.execute_script(
                    "return Array.from(document.querySelectorAll('a')).map(a => a.href || '')"
                )
            except Exception:
                raw_hrefs = []

            if not isinstance(raw_hrefs, list) or not raw_hrefs:
                try:
                    raw_hrefs = [
                        el.get_attribute("href") or ""
                        for el in driver.find_elements(By.TAG_NAME, "a")
                    ]
                except Exception:
                    pass

            new_in_iteration = 0
            if isinstance(raw_hrefs, list):
                for href in raw_hrefs:
                    if not href or "/reel/" not in href:
                        continue
                    m = re.search(r"/reel/([a-zA-Z0-9_-]+)", href)
                    code = m.group(1) if m else extract_instagram_id(href)
                    if code and code not in seen_codes:
                        seen_codes.add(code)
                        collected_urls.append(f"https://www.instagram.com/reel/{code}/")
                        new_in_iteration += 1
                        if code not in processed_ids:
                            unprocessed_candidate_count += 1

            if unprocessed_candidate_count >= max_videos:
                break

            if new_in_iteration == 0:
                no_new_links_count += 1
                if no_new_links_count >= 5:
                    break
            else:
                no_new_links_count = 0

            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                break
            time.sleep(2.0)

        logger.debug(
            f"Selenium reels page: {driver.current_url}, title: '{driver.title}', "
            f"found reels: {len(collected_urls)}"
        )

        # Fallback to main profile page if /{username}/reels/ yielded 0 reels
        if not collected_urls:
            main_url = f"https://www.instagram.com/{username}/"
            try:
                driver.get(main_url)
                time.sleep(3.0)
                for _ in range(max_scrolls):
                    raw_hrefs = []
                    try:
                        raw_hrefs = driver.execute_script(
                            "return Array.from(document.querySelectorAll('a')).map(a => a.href || '')"
                        )
                    except Exception:
                        raw_hrefs = []

                    if not isinstance(raw_hrefs, list) or not raw_hrefs:
                        try:
                            raw_hrefs = [
                                el.get_attribute("href") or ""
                                for el in driver.find_elements(By.TAG_NAME, "a")
                            ]
                        except Exception:
                            pass

                    if isinstance(raw_hrefs, list):
                        for href in raw_hrefs:
                            if not href or ("/reel/" not in href and "/p/" not in href):
                                continue
                            m = re.search(r"/(?:reel|p)/([a-zA-Z0-9_-]+)", href)
                            code = m.group(1) if m else extract_instagram_id(href)
                            if code and code not in seen_codes:
                                seen_codes.add(code)
                                collected_urls.append(f"https://www.instagram.com/reel/{code}/")
                    if len(collected_urls) >= max_videos:
                        break
                    try:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    except Exception:
                        break
                    time.sleep(2.0)
            except Exception as e:
                logger.debug(f"Selenium main profile fallback exception: {e}")

    except Exception as exc:
        logger.warning(f"Błąd podczas pobierania rolek przez Selenium dla @{username}: {exc}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    if not collected_urls:
        logger.debug(f"Selenium nie znalazło żadnych linków do rolek na profilu @{username}")
        return []

    logger.debug(f"Selenium znalazło {len(collected_urls)} linków do rolek dla @{username}. Weryfikacja metadanych...")

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    min_date = (
        datetime.now(timezone.utc) - timedelta(days=min_days)
        if min_days > 0
        else None
    )
    display_name = channel_name or username
    collected: List[Tuple[str, str, str, str]] = []

    for reel_url in collected_urls:
        shortcode = extract_instagram_id(reel_url)
        if not shortcode or shortcode in processed_ids:
            logger.debug(f"Pominięto już przetworzoną rolkę ID: {shortcode}")
            continue

        details = get_reel_details_from_url(reel_url, skip_verification=True)
        if not details:
            continue

        url, title, pub_date_str, uploader = details

        # Check date filter
        try:
            pub_dt = datetime.strptime(pub_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if pub_dt < cutoff_date:
                logger.debug(f"Pominięto rolkę {shortcode} z daty {pub_date_str} (starsza niż {days} dni)")
                continue
            if min_date and pub_dt > min_date:
                logger.debug(f"Pominięto rolkę {shortcode} z daty {pub_date_str} (nowsza niż {min_days} dni)")
                continue
        except Exception:
            pass

        # Check title filters
        if title_filters:
            caption = get_instagram_post_caption(reel_url) or ""
            combined_text = f"{title} {caption}".lower()
            if not any(f.lower() in combined_text for f in title_filters):
                logger.debug(f"Pominięto rolkę {shortcode} - brak dopasowania do filtrów: {title_filters}")
                continue

        final_uploader = display_name if display_name != username else uploader
        collected.append((reel_url, title, pub_date_str, final_uploader))

        if len(collected) >= max_videos:
            break

    logger.info(f"Zebrano {len(collected)} nowych rolek przez Headless Chrome dla @{username}")
    return collected


def get_reels_from_profile(
    profile_id_or_url: str,
    days: int = 3,
    max_videos: int = 10,
    skip_verification: bool = False,
    channel_name: Optional[str] = None,
    title_filters: Optional[List[str]] = None,
    min_days: int = 0,
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
        min_days: Minimum age of videos in days

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
        min_days=min_days,
    )
    if reels_api is not None:
        return reels_api

    # Strategy 2: Selenium Headless Browser fallback (bypasses bot filters, handles /{username}/reels/)
    reels_sel = _get_reels_from_profile_selenium(
        username=username,
        days=days,
        max_videos=max_videos,
        skip_verification=skip_verification,
        channel_name=display_name,
        title_filters=title_filters,
        cookie_file=cookie_file,
        min_days=min_days,
    )
    if reels_sel is not None:
        return reels_sel

    # Strategy 3: yt-dlp profile extractor
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
                min_date = (
                    datetime.now(timezone.utc) - timedelta(days=min_days)
                    if min_days > 0
                    else None
                )
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
                        if min_date and pub_dt > min_date:
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

    # Strategy 4: Instaloader fallback
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
