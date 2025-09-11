"""Kindle delivery utilities.

Responsibilities:
    * Automatically sending long notes (word-count based) as they are produced.
    * Re-sending an already processed single-video note (fast path) when invoked with --url --kindle.
    * Sending freshly processed results for a single video (even if below threshold).

Environment variables used:
    KINDLE_EMAIL            -> target Kindle recipient (required for sending)
    KINDLE_MIN_WORDS        -> integer threshold for auto-send (default 2000)
    SUMMARIES_PATH          -> base directory containing markdown summaries

Processing pipeline produces result dictionaries like:
    { 'path': '.../file.md', 'word_count': 2345 }
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Dict, Tuple

from yt2md.youtube import extract_video_id
from yt2md.video_index import find_markdown_files_for_video, get_processed_video_ids

from yt2md.logger import get_logger

logger = get_logger("kindle")


def _get_kindle_recipient() -> str | None:
    return os.getenv("KINDLE_EMAIL")


def convert_md_to_epub(md_path: Path):
    """Convert a markdown file to EPUB using existing converter."""
    from yt2md.email.epub.converter import md_to_epub, EpubOptions

    return md_to_epub(str(md_path), options=EpubOptions())


def send_epub(epub_path: Path, recipient: str, *, subject: str, body: str) -> bool:
    from yt2md.email.send_email import send_email

    return send_email(
        subject=subject,
        body=body,
        recipients=recipient,
        attachments=[str(epub_path)],
    )


def auto_send_long_notes(results: Iterable[Dict], *, threshold: int | None = None) -> Tuple[int, int]:
    """Auto-send notes whose word_count >= threshold.

    Returns (sent_count, failed_count).
    """
    recipient = _get_kindle_recipient()
    if not recipient:
        logger.debug("KINDLE_EMAIL not set; skipping auto-send of long notes")
        return (0, 0)

    if threshold is None:
        try:
            threshold = int(os.getenv("KINDLE_MIN_WORDS", "2000"))
        except ValueError:
            threshold = 2000

    long_notes = [r for r in results if r.get("word_count", 0) >= threshold]
    if not long_notes:
        logger.debug("No notes exceeded Kindle length threshold; nothing auto-sent")
        return (0, 0)

    from yt2md.email.epub.converter import md_to_epub, EpubOptions
    from yt2md.email.send_email import send_email

    sent = 0
    failed = 0
    for note in long_notes:
        md_path = note.get("path")
        if not md_path:
            continue
        try:
            epub_path = md_to_epub(md_path, options=EpubOptions())
            body = f"Auto-sent long note ({note.get('word_count')} words)."
            ok = send_email(
                subject="Kindle Delivery",
                body=body,
                recipients=recipient,
                attachments=[str(epub_path)],
            )
            if ok:
                logger.info(f"Auto Kindle send success: {md_path}")
                sent += 1
            else:
                logger.error(f"Auto Kindle send FAILED: {md_path}")
                failed += 1
        except Exception as e:  # noqa: BLE001
            logger.error(f"Auto Kindle conversion/send failed for {md_path}: {e}")
            failed += 1
    return (sent, failed)


def resend_latest_for_video_url(video_url: str) -> bool:
    """Attempt to resend the latest existing markdown for a processed video.

    Returns True if resent (and email attempted), False if not found / not processed.
    """
    recipient = _get_kindle_recipient()
    if not recipient:
        return False
    vid = extract_video_id(video_url)
    if not vid:
        return False
    processed = get_processed_video_ids(False)
    if vid not in processed:
        return False
    existing = find_markdown_files_for_video(vid)
    if not existing:
        return False
    existing.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    latest_md = existing[0]
    try:
        epub_path = convert_md_to_epub(Path(latest_md))
        ok = send_epub(epub_path, recipient, subject="Kindle Delivery", body="Resent existing note.")
        if ok:
            logger.info(f"Kindle resend successful: {latest_md}")
        else:
            logger.error(f"Kindle resend failed: {latest_md}")
        return ok
    except Exception as e:  # pragma: no cover
        logger.error(f"Resend conversion error: {e}")
        return False


def send_processed_results(results: Iterable[Dict]) -> Tuple[int, int]:
    """Send all processed markdown results for a single video (URL mode).

    Returns (sent, failed). Sends regardless of word count (single video explicit send).
    """
    recipient = _get_kindle_recipient()
    if not recipient:
        logger.error("KINDLE_EMAIL not set; cannot send processed results")
        return (0, 0)
    from yt2md.email.epub.converter import md_to_epub, EpubOptions
    from yt2md.email.send_email import send_email
    sent = 0
    failed = 0
    for r in results:
        md_path = r.get("path") if isinstance(r, dict) else None
        if not md_path:
            continue
        try:
            epub_path = md_to_epub(md_path, options=EpubOptions())
            ok = send_email(
                subject="Kindle Delivery",
                body="Delivered processed note.",
                recipients=recipient,
                attachments=[str(epub_path)],
            )
            if ok:
                logger.info(f"Kindle send success: {md_path}")
                sent += 1
            else:
                logger.error(f"Kindle send failed: {md_path}")
                failed += 1
        except Exception as e:  # pragma: no cover
            logger.error(f"Kindle conversion/send error for {md_path}: {e}")
            failed += 1
    return (sent, failed)

__all__ = [
    "auto_send_long_notes",
    "resend_latest_for_video_url",
    "send_processed_results",
    "convert_md_to_epub",
]
