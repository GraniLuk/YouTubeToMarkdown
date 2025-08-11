"""
Utilities for processing model responses from LLM providers.

Currently contains logic to extract an optional one-line description from the
first chunk of a response and to return the remaining content for further use.
"""

from __future__ import annotations

import re
from typing import Tuple


def process_model_response(text: str, is_first_chunk: bool) -> Tuple[str, str]:
    """
    Process model response to extract description and clean up text.

    Rules:
    - Only attempt to extract a description if this is the first chunk.
    - The description line starts with "DESCRIPTION:" or "OPIS:" (case-insensitive),
      may have leading whitespace, and may have extra spaces around the colon.
    - If found, return the text after that line and the extracted description value.
    - If not found or not the first chunk, return the original text and an empty description.

    Args:
        text: The raw model response text.
        is_first_chunk: Whether this is the first chunk of the response.

    Returns:
        tuple[str, str]: (processed_text, description)
    """
    description = ""

    if not is_first_chunk:
        return text, description

    lines = text.splitlines()

    # Regex: optional leading spaces, then DESCRIPTION or OPIS, optional spaces, colon, optional spaces, capture rest
    pattern = re.compile(r"^\s*(description|opis)\s*:\s*(.*)$", re.IGNORECASE)

    description_index = -1
    for idx, line in enumerate(lines):
        m = pattern.match(line)
        if m:
            description = m.group(2).strip()
            description_index = idx
            break

    if description_index != -1:
        text = "\n".join(lines[description_index + 1 :])

    return text, description


__all__ = ["process_model_response"]
