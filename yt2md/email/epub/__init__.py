"""EPUB conversion package.

Provides functionality to convert Markdown (.md) files produced by yt2md into
EPUB e-book files using the Pandoc CLI.

High-level usage:

from yt2md.email.epub import md_to_epub
output_path = md_to_epub("path/to/file.md")

This will return the path to the generated .epub file.
"""
from .converter import (
    md_to_epub,
    PandocNotAvailableError,
    EpubConversionError,
    EpubOptions,
)

__all__ = [
    "md_to_epub",
    "PandocNotAvailableError",
    "EpubConversionError",
    "EpubOptions",
]
