"""Dropbox Podcast RSS Exporter module for yt2md.

Downloads audio from YouTube using yt-dlp, uploads to Dropbox,
and maintains an RSS 2.0 podcast feed for AntennaPod.
"""

from email.utils import formatdate
import os
import re
import tempfile
import time
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET

import dropbox
from dropbox.exceptions import ApiError
from dropbox.files import WriteMode
import yt_dlp

from yt2md.audio_fallback import _get_ytdlp_auth_opts, _get_ytdlp_base_opts
from yt2md.logger import get_logger

logger = get_logger("podcast")


def get_dropbox_client() -> dropbox.Dropbox:
    """Initialize and return a Dropbox client using environment variables.

    Supports either DROPBOX_ACCESS_TOKEN directly, or
    DROPBOX_REFRESH_TOKEN + DROPBOX_APP_KEY + DROPBOX_APP_SECRET.
    """
    access_token = os.getenv("DROPBOX_ACCESS_TOKEN")
    refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN")
    app_key = os.getenv("DROPBOX_APP_KEY")
    app_secret = os.getenv("DROPBOX_APP_SECRET")
    timeout = 900  # 15 minutes timeout for large audio files

    if access_token:
        logger.debug("Using DROPBOX_ACCESS_TOKEN for authentication")
        return dropbox.Dropbox(access_token, timeout=timeout)
    elif refresh_token and app_key and app_secret:
        logger.debug("Using DROPBOX_REFRESH_TOKEN with App Key/Secret for authentication")
        return dropbox.Dropbox(
            oauth2_refresh_token=refresh_token,
            app_key=app_key,
            app_secret=app_secret,
            timeout=timeout,
        )
    else:
        raise ValueError(
            "Brak konfiguracji Dropbox API w pliku .env!\n"
            "Ustaw DROPBOX_ACCESS_TOKEN lub zestaw (DROPBOX_REFRESH_TOKEN, DROPBOX_APP_KEY, DROPBOX_APP_SECRET)."
        )


def sanitize_filename(filename: str) -> str:
    """Remove unsafe characters from filename."""
    return re.sub(r'[\\/*?:"<>|]', "", filename).strip()


def upload_file_to_dropbox(dbx: dropbox.Dropbox, local_path: str, dropbox_path: str) -> None:
    """Upload a local file to Dropbox using retries and chunked session for large files."""
    file_size = os.path.getsize(local_path)
    file_size_mb = file_size / (1024 * 1024)
    logger.info(f"📤 Wysyłanie pliku na Dropbox: {dropbox_path} ({file_size_mb:.2f} MB)...")

    SINGLE_UPLOAD_LIMIT = 150 * 1024 * 1024  # 150MB single request limit
    CHUNK_SIZE = 64 * 1024 * 1024           # 64MB max speed chunks

    with open(local_path, "rb") as f:
        if file_size <= SINGLE_UPLOAD_LIMIT:
            # Simple upload with retries
            for attempt in range(1, 4):
                try:
                    f.seek(0)
                    dbx.files_upload(f.read(), dropbox_path, mode=WriteMode.overwrite)
                    return
                except Exception as e:
                    if attempt == 3:
                        raise e
                    logger.warning(f"⚠️ Błąd wysyłania (próba {attempt}/3): {e}. Ponawianie za 5s...")
                    time.sleep(5)
        else:
            # Chunked upload session for large files with retries per chunk
            logger.info(f"Plik powyżej 150MB ({file_size_mb:.1f}MB) - wysyłanie w dużych paczkach po 64MB z automatycznym ponawianiem...")

            session_start_data = f.read(CHUNK_SIZE)
            upload_session_start_result = None

            for attempt in range(1, 4):
                try:
                    upload_session_start_result = dbx.files_upload_session_start(session_start_data)
                    break
                except Exception as e:
                    if attempt == 3:
                        raise e
                    logger.warning(f"⚠️ Błąd startu sesji uploadu (próba {attempt}/3): {e}. Ponawianie za 5s...")
                    time.sleep(5)

            if upload_session_start_result is None:
                raise RuntimeError("Nie udało się rozpocząć sesji wysyłania do Dropboxa.")

            cursor = dropbox.files.UploadSessionCursor(
                session_id=upload_session_start_result.session_id, offset=f.tell()
            )
            commit = dropbox.files.CommitInfo(path=dropbox_path, mode=WriteMode.overwrite)

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
                        break
                    except Exception as e:
                        if attempt == 3:
                            raise e
                        logger.warning(f"⚠️ Błąd wysyłania fragmentu pliku (próba {attempt}/3): {e}. Ponawianie za 5s...")
                        time.sleep(5)



def get_direct_raw_link(dbx: dropbox.Dropbox, dropbox_path: str) -> str:
    """Get or create a direct raw download link (`raw=1`) for a Dropbox file path."""
    try:
        shared_link_metadata = dbx.sharing_create_shared_link_with_settings(dropbox_path)
        url = shared_link_metadata.url
    except Exception:
        # Link already exists or creation failed, try listing existing shared links
        try:
            links = dbx.sharing_list_shared_links(path=dropbox_path).links
            if links:
                url = links[0].url
            else:
                raise RuntimeError(f"Nie udało się utworzyć ani pobrać udostępnionego linku dla {dropbox_path}")
        except Exception as err:
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


def fetch_or_create_rss_xml(dbx: dropbox.Dropbox, rss_path: str = "/podcast.xml") -> ET.ElementTree:
    """Download existing podcast.xml from Dropbox or create a new RSS 2.0 structure."""
    try:
        _, res = dbx.files_download(rss_path)
        xml_content = res.content
        logger.debug("Pobrano istniejący plik podcast.xml z Dropboxa")
        root = ET.fromstring(xml_content)
        return ET.ElementTree(root)
    except Exception as e:
        logger.debug(f"Plik {rss_path} nie istnieje na Dropboxie ({type(e).__name__}). Tworzenie nowego feedu RSS...")
        root = ET.Element("rss", {
            "version": "2.0",
            "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
        })
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


def update_rss_feed(
    tree: ET.ElementTree,
    video_title: str,
    video_url: str,
    audio_direct_url: str,
    file_size: int,
    duration_seconds: int,
    description: str,
    video_id: str,
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
            logger.info(f"Odcinek '{video_title}' (ID: {video_id}) już istnieje w RSS. Aktualizowanie linku...")
            enclosure = existing_item.find("enclosure")
            if enclosure is not None:
                enclosure.set("url", audio_direct_url)
                enclosure.set("length", str(file_size))
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

    ET.SubElement(item, "enclosure", {
        "url": audio_direct_url,
        "length": str(file_size),
        "type": "audio/mpeg",
    })

    if duration_seconds > 0:
        itunes_duration = ET.SubElement(item, "itunes:duration")
        m, s = divmod(duration_seconds, 60)
        h, m = divmod(m, 60)
        itunes_duration.text = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    # Insert new episode at top of channel
    items = channel.findall("item")
    if items:
        first_item_index = list(channel).index(items[0])
        channel.insert(first_item_index, item)
    else:
        channel.append(item)


def clean_old_episodes(dbx: dropbox.Dropbox, tree: ET.ElementTree, max_episodes: int) -> None:
    """Ensure the RSS feed has no more than `max_episodes`. Delete excess audio files from Dropbox."""
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        return

    items = channel.findall("item")
    if len(items) <= max_episodes:
        return

    logger.info(f"🧹 Przekroczono limit {max_episodes} odcinków w RSS (obecnie: {len(items)}). Czyszczenie najstarszych...")
    excess_items = items[max_episodes:]

    for item in excess_items:
        enclosure = item.find("enclosure")
        title_elem = item.find("title")
        ep_title = title_elem.text if title_elem is not None else "Nieznany odcinek"

        if enclosure is not None:
            url = enclosure.get("url", "")
            if url:
                parsed_path = urlparse(url).path
                filename = os.path.basename(unquote(parsed_path))
                if filename and filename.endswith((".mp3", ".m4a", ".webm", ".opus")):
                    dropbox_file_path = f"/{filename}"
                    try:
                        logger.info(f"🗑️ Automatyczne usuwanie pliku z Dropboxa: {dropbox_file_path} ('{ep_title}')")
                        dbx.files_delete_v2(dropbox_file_path)
                    except Exception as e:
                        logger.warning(f"Nie udało się usunąć pliku {dropbox_file_path} z Dropboxa: {e}")

        channel.remove(item)


def process_podcast_download(video_url: str) -> None:
    """Download YouTube audio, upload to Dropbox, update RSS feed and display link."""
    logger.info(f"🎧 Przetwarzanie trybu Podcast dla: {video_url}")

    # 1. Initialize Dropbox client
    dbx = get_dropbox_client()

    # 2. Extract metadata and download audio using yt-dlp
    base_opts = _get_ytdlp_base_opts()
    auth_opts = _get_ytdlp_auth_opts()

    with tempfile.TemporaryDirectory() as temp_dir:
        download_tmpl = os.path.join(temp_dir, "%(id)s.%(ext)s")
        ydl_opts = {
            **base_opts,
            **auth_opts,
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "outtmpl": download_tmpl,
        }

        logger.info("📥 Pobieranie audio z YouTube za pomocą yt-dlp...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_title = info.get("title", "Podcast Episode")
            video_id = info.get("id", str(int(time.time())))
            duration = info.get("duration", 0)
            description = info.get("description", "")

        audio_file = os.path.join(temp_dir, f"{video_id}.mp3")
        if not os.path.exists(audio_file):
            files = [f for f in os.listdir(temp_dir) if f.endswith((".mp3", ".m4a", ".webm", ".opus"))]
            if files:
                audio_file = os.path.join(temp_dir, files[0])
            else:
                raise FileNotFoundError("Nie udało się odnaleźć pobranego pliku audio.")

        file_size = os.path.getsize(audio_file)
        safe_title = sanitize_filename(video_title)
        dropbox_audio_path = f"/{safe_title}_{video_id}.mp3"

        # 3. Upload audio to Dropbox
        upload_file_to_dropbox(dbx, audio_file, dropbox_audio_path)

        # 4. Get direct raw URL for audio
        audio_raw_url = get_direct_raw_link(dbx, dropbox_audio_path)
        logger.debug(f"Direct raw audio URL: {audio_raw_url}")

        # 5. Fetch or create podcast.xml
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

        # 9. Structured Summary
        import colorama
        from yt2md.logger import colored_text

        logger.info("=" * 60)
        logger.info(colored_text("PODCAST PROCESSED SUCCESSFULLY!", colorama.Fore.GREEN + colorama.Style.BRIGHT))
        logger.info("=" * 60)
        logger.info(colored_text(f"Title: {video_title}", colorama.Fore.CYAN))
        logger.info(colored_text(f"File:  {dropbox_audio_path}", colorama.Fore.CYAN))
        logger.info("-" * 60)
        logger.info(colored_text("AntennaPod RSS Feed URL:", colorama.Fore.YELLOW + colorama.Style.BRIGHT))
        logger.info(colored_text(rss_raw_url, colorama.Fore.GREEN + colorama.Style.BRIGHT))
        logger.info("=" * 60)

