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

    # Regex: optional leading spaces, optional markdown formatting (**), 
    # then DESCRIPTION or OPIS, optional markdown formatting (**), optional spaces, colon, optional spaces, capture rest
    # But be more careful about the markdown - only match ** at the start and end, not in between
    pattern = re.compile(r"^\s*\**(description|opis)\**\s*:\s*(.*)$", re.IGNORECASE)

    description_index = -1
    inline_found = False
    for idx, line in enumerate(lines):
        m = pattern.match(line)
        if m:
            description_index = idx
            inline_value = m.group(2).strip()
            # Only consider it inline if there's meaningful content (not just whitespace, asterisks, or empty)
            if inline_value and not re.match(r'^[\s\*]*$', inline_value):
                description = inline_value
                inline_found = True
            break

    if description_index != -1:
        # If description is not inline, find the first non-empty line after the marker
        if not inline_found:
            for j in range(description_index + 1, len(lines)):
                candidate = lines[j].strip()
                if candidate:
                    description = candidate
                    # Exclude this candidate line as part of the description from the remaining text
                    text = "\n".join(lines[j + 1 :])
                    break
            else:
                # No non-empty lines after the marker
                text = "\n".join(lines[description_index + 1 :])
        else:
            # Inline description; keep the remainder after the marker line as content
            text = "\n".join(lines[description_index + 1 :])

    return text, description


__all__ = ["process_model_response"]
