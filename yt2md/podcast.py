"""Dropbox Podcast RSS Exporter module for yt2md.

Downloads audio from YouTube using yt-dlp, uploads to Dropbox,
and maintains an RSS 2.0 podcast feed for AntennaPod.
"""

import os
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from email.utils import formatdate
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse

import dropbox
import yt_dlp
from dropbox.exceptions import ApiError
from dropbox.files import WriteMode

from yt2md.audio_fallback import _get_ytdlp_auth_opts, _get_ytdlp_base_opts
from yt2md.logger import get_logger

logger = get_logger("podcast")

ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

ET.register_namespace("itunes", ITUNES_NS)
ET.register_namespace("content", CONTENT_NS)



def get_dropbox_client() -> dropbox.Dropbox:
    """Initialize and return a Dropbox client using environment variables.

    Supports either DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET (recommended),
    or DROPBOX_ACCESS_TOKEN directly.
    """
    access_token = os.getenv("DROPBOX_ACCESS_TOKEN")
    refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN")
    app_key = os.getenv("DROPBOX_APP_KEY")
    app_secret = os.getenv("DROPBOX_APP_SECRET")
    timeout = 300  # 5 minutes timeout for HTTP requests

    if refresh_token and app_key and app_secret:
        logger.debug(
            "Using DROPBOX_REFRESH_TOKEN with App Key/Secret for authentication"
        )
        return dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=app_key,
            app_secret=app_secret,
            timeout=timeout,
        )
    elif access_token:
        logger.debug("Using DROPBOX_ACCESS_TOKEN for authentication")
        return dropbox.Dropbox(access_token, timeout=timeout)
    else:
        raise ValueError(
            "Brak konfiguracji Dropbox API w pliku .env!\n"
            "Ustaw DROPBOX_ACCESS_TOKEN lub zestaw (DROPBOX_REFRESH_TOKEN, DROPBOX_APP_KEY, DROPBOX_APP_SECRET)."
        )


def sanitize_filename(filename: str) -> str:
    """Remove unsafe characters from filename."""
    return re.sub(r'[\\/*?:"<>|]', "", filename).strip()


def upload_file_to_dropbox(
    dbx: dropbox.Dropbox, local_path: str, dropbox_path: str
) -> None:
    """Upload a local file to Dropbox using retries, 16MB chunked session and progress logging."""
    file_size = os.path.getsize(local_path)
    file_size_mb = file_size / (1024 * 1024)
    logger.info(
        f"📤 Wysyłanie pliku na Dropbox: {dropbox_path} ({file_size_mb:.2f} MB)..."
    )

    SINGLE_UPLOAD_LIMIT = 8 * 1024 * 1024  # 8MB single request limit
    CHUNK_SIZE = 4 * 1024 * 1024  # 4MB chunks for max stability on variable upload speeds

    upload_start_time = time.time()

    def _log_progress(current_bytes: int, total_bytes: int) -> None:
        import sys
        import colorama

        pct = (current_bytes / total_bytes) * 100
        mb_curr = current_bytes / (1024 * 1024)
        mb_total = total_bytes / (1024 * 1024)
        bar_len = 20
        filled_len = int(bar_len * current_bytes // total_bytes)
        bar = "█" * filled_len + "░" * (bar_len - filled_len)

        elapsed = time.time() - upload_start_time
        if elapsed > 0 and current_bytes > 0:
            speed_mbps = (current_bytes / (1024 * 1024)) / elapsed
            remaining_bytes = total_bytes - current_bytes
            eta_secs = remaining_bytes / (current_bytes / elapsed) if current_bytes > 0 else 0
            if eta_secs >= 60:
                eta_str = f"{int(eta_secs // 60)}m {int(eta_secs % 60):02d}s"
            else:
                eta_str = f"{int(eta_secs)}s"
            meta_str = f" • {speed_mbps:.1f} MB/s • ETA: {eta_str}"
        else:
            meta_str = " • ETA: --"

        logger.debug(f"Upload progress: [{bar}] {mb_curr:.1f}/{mb_total:.1f}MB ({pct:.0f}%)")

        colored_bar = f"{colorama.Fore.CYAN}[{bar}]{colorama.Style.RESET_ALL}"
        colored_pct = f"{colorama.Fore.GREEN}{pct:.0f}%{colorama.Style.RESET_ALL}"
        colored_meta = f"{colorama.Fore.YELLOW}{meta_str}{colorama.Style.RESET_ALL}"
        sys.stdout.write(
            f"\r📤 Postęp wysyłania: {colored_bar} {mb_curr:.1f} / {mb_total:.1f} MB ({colored_pct}){colored_meta}   "
        )
        sys.stdout.flush()
        if current_bytes >= total_bytes:
            sys.stdout.write("\n")
            sys.stdout.flush()

    with open(local_path, "rb") as f:
        if file_size <= SINGLE_UPLOAD_LIMIT:
            # Simple upload with retries
            for attempt in range(1, 4):
                try:
                    f.seek(0)
                    dbx.files_upload(f.read(), dropbox_path, mode=WriteMode.overwrite)
                    _log_progress(file_size, file_size)
                    return
                except Exception as e:
                    if _is_auth_error(e):
                        _raise_auth_error(e)
                    if attempt == 3:
                        raise e
                    logger.warning(
                        f"⚠️ Błąd wysyłania (próba {attempt}/3): {e}. Ponawianie za 3s..."
                    )
                    time.sleep(3)
        else:
            # Chunked upload session for large files with retries per chunk
            session_start_data = f.read(CHUNK_SIZE)
            upload_session_start_result = None

            for attempt in range(1, 4):
                try:
                    upload_session_start_result = dbx.files_upload_session_start(
                        session_start_data
                    )
                    break
                except Exception as e:
                    if _is_auth_error(e):
                        _raise_auth_error(e)
                    if attempt == 3:
                        raise e
                    logger.warning(
                        f"⚠️ Błąd startu sesji uploadu (próba {attempt}/3): {e}. Ponawianie za 3s..."
                    )
                    time.sleep(3)

            if upload_session_start_result is None:
                raise RuntimeError(
                    "Nie udało się rozpocząć sesji wysyłania do Dropboxa."
                )

            cursor = dropbox.files.UploadSessionCursor(
                session_id=upload_session_start_result.session_id, offset=f.tell()
            )
            commit = dropbox.files.CommitInfo(
                path=dropbox_path, mode=WriteMode.overwrite
            )

            _log_progress(f.tell(), file_size)

            while f.tell() < file_size:
                chunk = f.read(CHUNK_SIZE)
                is_last_chunk = f.tell() >= file_size

                for attempt in range(1, 4):
                    try:
                        if is_last_chunk:
                            dbx.files_upload_session_finish(chunk, cursor, commit)
                        else:
                            dbx.files_upload_session_append_v2(chunk, cursor)
                            cursor.offset = f.tell()
                        _log_progress(f.tell(), file_size)
                        break
                    except Exception as e:
                        if _is_auth_error(e):
                            _raise_auth_error(e)
                        if attempt == 3:
                            raise e
                        logger.warning(
                            f"⚠️ Błąd wysyłania fragmentu pliku (próba {attempt}/3): {e}. Ponawianie za 3s..."
                        )
                        time.sleep(3)


def get_direct_raw_link(dbx: dropbox.Dropbox, dropbox_path: str) -> str:
    """Get or create a direct raw download link (`raw=1`) for a Dropbox file path."""
    try:
        shared_link_metadata = dbx.sharing_create_shared_link_with_settings(
            dropbox_path
        )
        url = shared_link_metadata.url
    except Exception as e:
        if _is_auth_error(e):
            _raise_auth_error(e)
        # Link already exists or creation failed, try listing existing shared links
        try:
            links = dbx.sharing_list_shared_links(path=dropbox_path).links
            if links:
                url = links[0].url
            else:
                raise RuntimeError(
                    f"Nie udało się utworzyć ani pobrać udostępnionego linku dla {dropbox_path}"
                )
        except Exception as err:
            if _is_auth_error(err):
                _raise_auth_error(err)
            raise err

    # Convert link to direct raw link
    if "dl=0" in url:
        raw_url = url.replace("dl=0", "raw=1")
    elif "dl=1" in url:
        raw_url = url.replace("dl=1", "raw=1")
    else:
        raw_url = url + "&raw=1" if "?" in url else url + "?raw=1"

    # Use dl.dropboxusercontent.com for maximum compatibility
    raw_url = raw_url.replace("www.dropbox.com", "dl.dropboxusercontent.com")
    return raw_url


def _is_auth_error(e: Exception) -> bool:
    """Check if an exception indicates a Dropbox authentication/token error."""
    err_str = str(e).lower()
    type_name = type(e).__name__.lower()
    if (
        "expired_access_token" in err_str
        or "invalid_access_token" in err_str
        or "autherror" in type_name
        or "autherror" in err_str
        or "validationerror" in type_name
        or "catch-all tag" in err_str
    ):
        return True
    return False


def _raise_auth_error(e: Exception) -> None:
    raise RuntimeError(
        "🔑 Twój token dostępowy Dropbox (DROPBOX_ACCESS_TOKEN) wygasł lub jest nieprawidłowy!\n"
        "Wygeneruj nowy token w panelu Dropbox App Console lub w pliku .env skonfiguruj bezterminowy zestaw (DROPBOX_REFRESH_TOKEN, DROPBOX_APP_KEY, DROPBOX_APP_SECRET)."
    ) from e


def _is_file_not_found_error(e: Exception) -> bool:
    """Check if exception from Dropbox API is a file not found error."""
    if isinstance(e, ApiError):
        if hasattr(e, "error") and e.error.is_path():
            path_err = e.error.get_path()
            if path_err.is_not_found():
                return True
    err_str = str(e).lower()
    if "not_found" in err_str or "not found" in err_str or "path_not_found" in err_str:
        return True
    return False


def fetch_or_create_rss_xml(
    dbx: dropbox.Dropbox, rss_path: str = "/podcast.xml"
) -> ET.ElementTree:
    """Download existing podcast.xml from Dropbox or create a new RSS 2.0 structure."""
    for attempt in range(1, 4):
        try:
            _, res = dbx.files_download(rss_path)
            xml_content = res.content
            logger.debug("Pobrano istniejący plik podcast.xml z Dropboxa")
            root = ET.fromstring(xml_content)
            return ET.ElementTree(root)
        except Exception as e:
            if _is_auth_error(e):
                _raise_auth_error(e)

            if _is_file_not_found_error(e):
                logger.info(
                    f"ℹ️ Plik {rss_path} nie istnieje na Dropboxie. Tworzenie nowego feedu RSS..."
                )
                root = ET.Element("rss", {"version": "2.0"})
                channel = ET.SubElement(root, "channel")
                title = ET.SubElement(channel, "title")
                title.text = "YT2MD Podcast Feed"
                link = ET.SubElement(channel, "link")
                link.text = "https://github.com/GraniLuk/YouTubeToMarkdown"
                desc = ET.SubElement(channel, "description")
                desc.text = "Pobrane utworów audio z YouTube dla AntennaPod"
                lang = ET.SubElement(channel, "language")
                lang.text = "pl-pl"
                return ET.ElementTree(root)

            if attempt < 3:
                logger.warning(
                    f"⚠️ Błąd pobierania {rss_path} z Dropboxa (próba {attempt}/3): {e}. Ponawianie za 3s..."
                )
                time.sleep(3)
            else:
                logger.error(
                    f"❌ Błąd pobierania {rss_path} z Dropboxa po 3 próbach: {e}"
                )
                raise e


def update_rss_feed(
    tree: ET.ElementTree,
    video_title: str,
    video_url: str,
    audio_direct_url: str,
    file_size: int,
    duration_seconds: int,
    description: str,
    video_id: str,
    mime_type: str = "audio/mp4",
) -> None:
    """Append a new episode item to the RSS feed ElementTree."""
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        channel = ET.SubElement(root, "channel")

    # Check for duplicates by guid
    for existing_item in channel.findall("item"):
        guid_elem = existing_item.find("guid")
        if guid_elem is not None and guid_elem.text == video_id:
            logger.info(
                f"Odcinek '{video_title}' (ID: {video_id}) już istnieje w RSS. Aktualizowanie linku..."
            )
            enclosure = existing_item.find("enclosure")
            if enclosure is not None:
                enclosure.set("url", audio_direct_url)
                enclosure.set("length", str(file_size))
                enclosure.set("type", mime_type)
            return

    # Create new item
    item = ET.Element("item")

    title_elem = ET.SubElement(item, "title")
    title_elem.text = video_title

    link_elem = ET.SubElement(item, "link")
    link_elem.text = video_url

    desc_elem = ET.SubElement(item, "description")
    desc_elem.text = description or video_title

    pubdate_elem = ET.SubElement(item, "pubDate")
    pubdate_elem.text = formatdate(time.time(), usegmt=True)

    guid_elem = ET.SubElement(item, "guid", {"isPermaLink": "false"})
    guid_elem.text = video_id

    ET.SubElement(
        item,
        "enclosure",
        {
            "url": audio_direct_url,
            "length": str(file_size),
            "type": mime_type,
        },
    )

    if duration_seconds > 0:
        itunes_duration = ET.SubElement(item, f"{{{ITUNES_NS}}}duration")
        m, s = divmod(duration_seconds, 60)
        h, m = divmod(m, 60)
        itunes_duration.text = (
            f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        )

    # Insert new episode at top of channel
    items = channel.findall("item")
    if items:
        first_item_index = list(channel).index(items[0])
        channel.insert(first_item_index, item)
    else:
        channel.append(item)


def clean_old_episodes(
    dbx: dropbox.Dropbox, tree: ET.ElementTree, max_episodes: int
) -> None:
    """Ensure the RSS feed has no more than `max_episodes`. Delete excess audio files from Dropbox."""
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        return

    items = channel.findall("item")

    # 1. Trim items in channel XML if exceeding max_episodes
    if len(items) > max_episodes:
        logger.info(
            f"🧹 Przekroczono limit {max_episodes} odcinków w RSS (obecnie: {len(items)}). Czyszczenie najstarszych..."
        )
        excess_items = items[max_episodes:]
        for item in excess_items:
            channel.remove(item)

    # 2. Collect active video IDs from current RSS items
    active_video_ids = set()
    for item_elem in channel.findall("item"):
        guid_elem = item_elem.find("guid")
        if guid_elem is not None and guid_elem.text:
            active_video_ids.add(guid_elem.text.strip())

    # 3. Clean up orphaned audio files on Dropbox that are not in active_video_ids
    try:
        res = dbx.files_list_folder("")
        audio_exts = (".mp3", ".m4a", ".webm", ".opus", ".ogg")
        for entry in res.entries:
            if not isinstance(entry, dropbox.files.FileMetadata):
                continue
            filename = entry.name
            if filename.lower().endswith(audio_exts):
                # Check if any active video_id is part of this filename
                is_active = any(
                    f"_{vid}." in filename
                    or filename.rsplit(".", 1)[0].endswith(f"_{vid}")
                    for vid in active_video_ids
                )
                if not is_active:
                    logger.info(
                        f"🗑️ Usuwanie starego pliku z Dropboxa: /{filename}..."
                    )
                    try:
                        dbx.files_delete_v2(f"/{filename}")
                        logger.info(
                            f"✅ Pomyślnie usunięto plik z Dropboxa: /{filename}"
                        )
                    except Exception as e:
                        logger.error(
                            f"❌ Nie udało się usunąć pliku /{filename} z Dropboxa: {e}"
                        )
    except Exception as e:
        logger.warning(
            f"Nie udało się pobrać listy plików z Dropboxa do czyszczenia: {e}"
        )


def process_podcast_download(
    video_url: str,
    dbx: Optional[dropbox.Dropbox] = None,
    tree: Optional[ET.ElementTree] = None,
) -> ET.ElementTree:
    """Download YouTube audio, upload to Dropbox, update RSS feed and display link."""
    logger.info(f"🎧 Przetwarzanie trybu Podcast dla: {video_url}")

    # 1. Initialize Dropbox client if not provided
    if dbx is None:
        dbx = get_dropbox_client()

    # 2. Extract metadata and download audio using yt-dlp (prefer native m4a without re-encoding)
    base_opts = _get_ytdlp_base_opts()
    auth_opts = _get_ytdlp_auth_opts()

    with tempfile.TemporaryDirectory() as temp_dir:
        download_tmpl = os.path.join(temp_dir, "%(id)s.%(ext)s")
        ydl_opts = {
            **base_opts,
            **auth_opts,
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": download_tmpl,
        }

        logger.info(
            "📥 Pobieranie natywnego strumienia audio z YouTube za pomocą yt-dlp..."
        )
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_title = info.get("title", "Podcast Episode")
            video_id = info.get("id", str(int(time.time())))
            duration = info.get("duration", 0)
            description = info.get("description", "")

        files = [
            f
            for f in os.listdir(temp_dir)
            if f.endswith((".m4a", ".mp3", ".webm", ".opus", ".ogg"))
        ]
        if not files:
            raise FileNotFoundError("Nie udało się odnaleźć pobranego pliku audio.")

        audio_file = os.path.join(temp_dir, files[0])
        ext = os.path.splitext(audio_file)[1].lower()
        file_size = os.path.getsize(audio_file)

        # Map extension to MIME type
        mime_map = {
            ".m4a": "audio/mp4",
            ".mp3": "audio/mpeg",
            ".webm": "audio/webm",
            ".opus": "audio/ogg",
            ".ogg": "audio/ogg",
        }
        mime_type = mime_map.get(ext, "audio/mp4")

        safe_title = sanitize_filename(video_title)
        dropbox_audio_path = f"/{safe_title}_{video_id}{ext}"

        # 3. Upload audio to Dropbox
        upload_file_to_dropbox(dbx, audio_file, dropbox_audio_path)

        # 4. Get direct raw URL for audio
        audio_raw_url = get_direct_raw_link(dbx, dropbox_audio_path)
        logger.debug(f"Direct raw audio URL: {audio_raw_url}")

        # 5. Fetch or create podcast.xml if not provided
        if tree is None:
            tree = fetch_or_create_rss_xml(dbx, "/podcast.xml")

        # 6. Update RSS feed
        update_rss_feed(
            tree,
            video_title=video_title,
            video_url=video_url,
            audio_direct_url=audio_raw_url,
            file_size=file_size,
            duration_seconds=duration,
            description=description,
            video_id=video_id,
            mime_type=mime_type,
        )

        # 6b. Clean up old episodes exceeding PODCAST_MAX_EPISODES limit
        try:
            max_episodes = int(os.getenv("PODCAST_MAX_EPISODES", "10"))
        except ValueError:
            max_episodes = 10
        clean_old_episodes(dbx, tree, max_episodes)

        # 7. Upload updated podcast.xml
        if hasattr(ET, "indent"):
            ET.indent(tree, space="  ")
        xml_bytes = ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True)

        logger.info("📤 Aktualizowanie pliku podcast.xml na Dropboxie...")
        dbx.files_upload(xml_bytes, "/podcast.xml", mode=WriteMode.overwrite)

        # 8. Get direct raw URL for podcast.xml
        rss_raw_url = get_direct_raw_link(dbx, "/podcast.xml")

        # 8b. Update local video index so yt2md collector skips this video ID
        try:
            from yt2md.video_index import update_video_index
            update_video_index(video_id, "PODCAST_PROCESSED")
        except Exception as index_err:
            logger.warning(f"Could not update video index: {index_err}")

        # 9. Structured Summary
        import colorama

        from yt2md.logger import colored_text

        logger.info("=" * 60)
        logger.info(
            colored_text(
                "PODCAST PROCESSED SUCCESSFULLY!",
                colorama.Fore.GREEN + colorama.Style.BRIGHT,
            )
        )
        logger.info("=" * 60)
        logger.info(colored_text(f"Title: {video_title}", colorama.Fore.CYAN))
        logger.info(colored_text(f"File:  {dropbox_audio_path}", colorama.Fore.CYAN))
        logger.info("-" * 60)
        logger.info(
            colored_text(
                "AntennaPod RSS Feed URL:",
                colorama.Fore.YELLOW + colorama.Style.BRIGHT,
            )
        )
        logger.info(
            colored_text(rss_raw_url, colorama.Fore.GREEN + colorama.Style.BRIGHT)
        )
        logger.info("=" * 60)

        return tree


def process_podcast_subscriptions(
    days: int = 3, channel_name: Optional[str] = None, max_videos: int = 10
) -> None:
    """Collect new videos from subscribed Podcast channels and export to Dropbox RSS."""
    logger.info("📡 Sprawdzanie subskrypcji podcastów (kategoria: Podcast w channels.yaml)...")
    from yt2md.video_collector import collect_videos_from_category

    videos_to_process = collect_videos_from_category(
        category="Podcast",
        days=days,
        channel_name=channel_name,
        max_videos=max_videos,
    )

    if not videos_to_process:
        logger.info("Brak nowych filmów w subskrypcjach kategorii Podcast.")
        return

    logger.info(f"Znaleziono {len(videos_to_process)} filmów z kanałów podcastowych.")

    # Get Dropbox client and fetch existing RSS feed
    dbx = get_dropbox_client()
    tree = fetch_or_create_rss_xml(dbx, "/podcast.xml")

    processed_count = 0
    for video_tuple in videos_to_process:
        video_url = video_tuple[0]
        video_title = video_tuple[1]

        # Extract YouTube video ID
        video_id = None
        if "v=" in video_url:
            video_id = video_url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in video_url:
            video_id = video_url.split("youtu.be/")[1].split("?")[0]

        # Re-check existing guids from current in-memory tree
        existing_guids = set()
        root = tree.getroot()
        for item_elem in root.findall(".//item"):
            guid_elem = item_elem.find("guid")
            if guid_elem is not None and guid_elem.text:
                existing_guids.add(guid_elem.text.strip())
            link_elem = item_elem.find("link")
            if link_elem is not None and link_elem.text:
                link_url = link_elem.text.strip()
                if "v=" in link_url:
                    existing_guids.add(link_url.split("v=")[1].split("&")[0])

        if video_id and video_id in existing_guids:
            logger.info(f"⏭️ Odcinek '{video_title}' (ID: {video_id}) już istnieje w RSS. Pomijanie.")
            continue

        logger.info(f"🎙️ Nowy odcinek podcastu: '{video_title}' ({video_url})")
        tree = process_podcast_download(video_url, dbx=dbx, tree=tree)
        processed_count += 1

    if processed_count == 0:
        logger.info("Wszystkie nowe odcinki z subskrypcji podcastowych zostały już dodane wcześniej.")


def process_podcast_playlist(
    playlist_url_or_id: str,
    dbx: Optional[dropbox.Dropbox] = None,
    tree: Optional[ET.ElementTree] = None,
    max_videos: int = 10,
    skip_verification: bool = False,
) -> Optional[ET.ElementTree]:
    """Download audio for new/unprocessed videos from a YouTube playlist and update podcast RSS feed."""
    logger.info(f"🎧 Przetwarzanie playlisty dla trybu Podcast: {playlist_url_or_id}")
    from yt2md.youtube import get_videos_from_playlist

    videos_to_process = get_videos_from_playlist(
        playlist_url_or_id,
        max_videos=max_videos,
        skip_verification=skip_verification,
    )

    if not videos_to_process:
        logger.info("Brak nowych filmów do przetworzenia w playliście.")
        if tree is None and dbx is not None:
            tree = fetch_or_create_rss_xml(dbx, "/podcast.xml")
        return tree

    if dbx is None:
        dbx = get_dropbox_client()
    if tree is None:
        tree = fetch_or_create_rss_xml(dbx, "/podcast.xml")

    processed_count = 0
    for video_url, video_title, _published_date, _uploader in videos_to_process:
        video_id = None
        if "v=" in video_url:
            video_id = video_url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in video_url:
            video_id = video_url.split("youtu.be/")[1].split("?")[0]

        # Re-check existing guids from current in-memory tree
        existing_guids = set()
        root = tree.getroot()
        for item_elem in root.findall(".//item"):
            guid_elem = item_elem.find("guid")
            if guid_elem is not None and guid_elem.text:
                existing_guids.add(guid_elem.text.strip())
            link_elem = item_elem.find("link")
            if link_elem is not None and link_elem.text:
                link_url = link_elem.text.strip()
                if "v=" in link_url:
                    existing_guids.add(link_url.split("v=")[1].split("&")[0])

        if video_id and video_id in existing_guids and not skip_verification:
            logger.info(f"⏭️ Odcinek '{video_title}' (ID: {video_id}) już istnieje w RSS. Pomijanie.")
            continue

        logger.info(f"🎙️ Nowy odcinek podcastu z playlisty: '{video_title}' ({video_url})")
        try:
            tree = process_podcast_download(video_url, dbx=dbx, tree=tree)
            processed_count += 1
        except Exception as e:
            logger.error(f"❌ Błąd podczas przetwarzania filmu '{video_title}' ({video_url}): {e}")
            continue

    logger.info(f"✅ Zakończono przetwarzanie playlisty. Pomyślnie dodano {processed_count} odcinków.")
    return tree


