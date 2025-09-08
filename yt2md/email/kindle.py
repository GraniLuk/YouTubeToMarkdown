"""Kindle delivery utilities.

This module centralizes logic for:
  * Sending the most recently modified markdown file as an EPUB to a Kindle address.
  * Automatically sending long notes (word-count based) after processing.

Environment variables used:
  KINDLE_EMAIL            -> target Kindle recipient (required for sending)
  KINDLE_MIN_WORDS        -> integer threshold for auto-send (default 2000)
  SUMMARIES_PATH          -> base directory containing markdown summaries

The processing pipeline (in `main.py`) produces a list of dict results like:
  { 'path': '.../file.md', 'word_count': 2345 }

Public functions:
  send_latest_markdown_to_kindle()
  auto_send_long_notes(results)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Dict, Tuple

from yt2md.logger import get_logger

logger = get_logger("kindle")


def _get_kindle_recipient() -> str | None:
    return os.getenv("KINDLE_EMAIL")


def _gather_markdown_files(summaries_dir: str) -> List[Path]:
    md_files: List[Path] = []
    for root, _dirs, files in os.walk(summaries_dir):
        for f in files:
            if f.lower().endswith(".md"):
                md_files.append(Path(root) / f)
    return md_files


def find_latest_markdown(summaries_dir: str) -> Path | None:
    """Return the most recently modified markdown file path or None."""
    try:
        all_md = _gather_markdown_files(summaries_dir)
        if not all_md:
            return None
        all_md.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return all_md[0]
    except Exception as e:  # pragma: no cover
        logger.error(f"Failed scanning markdown files: {e}")
        return None


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


def send_latest_markdown_to_kindle() -> bool:
    """Locate newest markdown, convert, and send to Kindle. Returns success boolean."""
    summaries_dir = os.getenv("SUMMARIES_PATH")
    if not summaries_dir:
        logger.error("SUMMARIES_PATH not set; cannot perform Kindle workflow")
        return False

    recipient = _get_kindle_recipient()
    if not recipient:
        logger.error("KINDLE_EMAIL not set; skipping Kindle send")
        return False

    latest_md = find_latest_markdown(summaries_dir)
    if not latest_md:
        logger.warning("No markdown files found for Kindle workflow")
        return False

    logger.info(f"Latest markdown selected for Kindle workflow: {latest_md}")
    try:
        epub_path = convert_md_to_epub(latest_md)
    except Exception as e:
        logger.error(f"EPUB conversion failed: {e}")
        return False

    logger.info(f"Generated EPUB: {epub_path}")
    ok = send_epub(epub_path, recipient, subject="Kindle Delivery", body="Automated delivery from yt2md --kindle workflow.")
    if ok:
        logger.info("Kindle email sent successfully")
    else:
        logger.error("Failed to send Kindle email")
    return ok


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

__all__ = [
    "send_latest_markdown_to_kindle",
    "auto_send_long_notes",
    "find_latest_markdown",
]
