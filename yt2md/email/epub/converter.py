"""Markdown to EPUB conversion utilities using Pandoc.

We intentionally shell out to the Pandoc CLI instead of relying on a thin
Python wrapper because the official and most complete feature surface is
exposed via the executable (see: https://pandoc.org/MANUAL.html).

Minimal feature goals for the first iteration:
- Convert a single markdown file to an EPUB3 file.
- Allow optional metadata overrides (title, author, cover image, css).
- Graceful degradation with clear exceptions if pandoc is not installed.
- Log the conversion steps via the central logger if available.

Future enhancements (not yet implemented):
- Batch conversion of multiple markdown files into one EPUB (concatenation).
- Support passing YAML metadata file.
- Embedding custom fonts (--epub-embed-font).
- Table of contents depth configuration.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

try:
    from yt2md.logger import get_logger  # type: ignore
except Exception:  # pragma: no cover - fallback if logger import path changes
    def get_logger(name: str = "epub"):  # type: ignore
        import logging
        return logging.getLogger(f"yt2md.{name}")


class PandocNotAvailableError(RuntimeError):
    """Raised when pandoc executable cannot be located in PATH."""


class EpubConversionError(RuntimeError):
    """Raised on non-zero pandoc exit or unexpected failures."""


@dataclass
class EpubOptions:
    title: Optional[str] = None
    author: Optional[str] = None
    cover_image: Optional[Path] = None
    css: Optional[Path] = None
    toc: bool = True
    toc_depth: int = 3
    split_level: int = 1  # maps to --split-level for internal file chunking
    extra_args: Sequence[str] | None = None


_PANDOC_CACHE = {"checked": False, "available": False, "path": None}


def _find_pandoc() -> str:
    if not _PANDOC_CACHE["checked"]:
        path = shutil.which("pandoc")
        _PANDOC_CACHE["checked"] = True
        _PANDOC_CACHE["available"] = path is not None
        _PANDOC_CACHE["path"] = path
    if not _PANDOC_CACHE["available"]:
        raise PandocNotAvailableError(
            "Pandoc executable not found in PATH. Install from https://pandoc.org/installing.html"
        )
    return _PANDOC_CACHE["path"]  # type: ignore


def md_to_epub(
    markdown_path: str | os.PathLike,
    output_path: str | os.PathLike | None = None,
    options: Optional[EpubOptions] = None,
) -> Path:
    """Convert a single Markdown file to an EPUB using pandoc.

    Parameters
    ----------
    markdown_path: Path to the input .md file.
    output_path: Optional explicit output .epub path. If omitted, uses same stem.
    options: Optional EpubOptions for metadata and formatting.

    Returns
    -------
    Path to the created EPUB file.

    Raises
    ------
    FileNotFoundError: if markdown file does not exist.
    PandocNotAvailableError: if pandoc executable is missing.
    EpubConversionError: on pandoc failure (non-zero exit code).
    """
    logger = get_logger("epub")
    md_path = Path(markdown_path)
    if not md_path.is_file():
        raise FileNotFoundError(f"Markdown file not found: {md_path}")

    pandoc_exe = _find_pandoc()

    if output_path is None:
        output_path = md_path.with_suffix(".epub")
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    opts = options or EpubOptions()

    cmd: list[str] = [
        pandoc_exe,
        str(md_path),
        "-o",
        str(out_path),
        "--to",
        "epub3",
        "--standalone",
        f"--split-level={opts.split_level}",
        f"--toc-depth={opts.toc_depth}",
    ]

    if opts.toc:
        cmd.append("--toc")

    metadata_vars: list[str] = []
    if opts.title:
        metadata_vars.extend(["-M", f"title={opts.title}"])
    if opts.author:
        metadata_vars.extend(["-M", f"author={opts.author}"])

    cmd.extend(metadata_vars)

    if opts.cover_image:
        cmd.append(f"--epub-cover-image={opts.cover_image}")
    if opts.css:
        cmd.append(f"--css={opts.css}")

    if opts.extra_args:
        cmd.extend(opts.extra_args)

    # Add a deterministic identifier for reproducibility if not provided via options.extra_args
    if not any(arg.startswith("--metadata=identifier=") or arg.startswith("-M") and "identifier=" in arg for arg in cmd):
        identifier = uuid.uuid4()
        cmd.extend(["-M", f"identifier=urn:uuid:{identifier}"])

    logger.info("Converting markdown to EPUB", extra={
        "event": "epub_conversion_start",
        "input": str(md_path),
        "output": str(out_path),
        "cmd": " ".join(cmd),
    })

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:
        raise EpubConversionError(f"Failed to execute pandoc: {e}") from e

    if completed.returncode != 0:
        logger.error(
            "Pandoc conversion failed",
            extra={
                "event": "epub_conversion_error",
                "returncode": completed.returncode,
                "stderr": completed.stderr[-2000:],
            },
        )
        raise EpubConversionError(
            f"Pandoc failed with exit code {completed.returncode}: {completed.stderr.strip().splitlines()[-1]}"
        )

    if not out_path.is_file():  # extremely unlikely if pandoc succeeded
        raise EpubConversionError("Pandoc reported success but output file was not created")

    logger.info(
        "EPUB conversion complete",
        extra={
            "event": "epub_conversion_complete",
            "output": str(out_path),
            "size_bytes": out_path.stat().st_size,
        },
    )

    return out_path

__all__ = ["md_to_epub", "EpubOptions", "PandocNotAvailableError", "EpubConversionError"]
