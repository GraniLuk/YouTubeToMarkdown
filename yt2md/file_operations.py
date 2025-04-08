import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from yt2md.google_drive import setup_google_drive, upload_to_drive


def get_script_dir():
    """Get the directory where the script is running from."""
    # If packaged with PyInstaller, use the _MEIPASS attribute
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    # Otherwise, use the directory of the script
    return os.path.abspath(os.path.dirname(__file__))


def sanitize_filename(filename):
    """Clean up a filename to make it valid for all platforms."""
    # Replace invalid characters with underscores
    filename = re.sub(r'[\\/:*?"<>|]', "_", filename)
    # Remove multiple spaces
    filename = re.sub(r"\s+", " ", filename)
    # Trim
    filename = filename.strip()
    return filename


def open_file(filepath):
    """Open a file with the default system application."""
    try:
        # Open file with default application
        os.startfile(filepath)
        return True
    except Exception as e:
        print(f"Error opening file {filepath}: {e}")
        return False


def save_to_markdown(
    title,
    video_url,
    content,
    author,
    published_date,
    description,
    category,
    suffix=None,
):
    """
    Save content to a markdown file in the Summaries directory.

    Args:
        title: The title of the video
        video_url: URL of the video
        content: The markdown content to save
        author: The author/channel name
        published_date: The date when the video was published
        description: Brief description of the content
        category: Category of the content
        suffix: Optional suffix to add to the filename (e.g., "Ollama")

    Returns:
        str: Path to the saved file
    """
    # Create the summaries directory if it doesn't exist
    summaries_dir = os.path.join(
        os.path.dirname(os.path.dirname(get_script_dir())), "Summaries"
    )
    os.makedirs(summaries_dir, exist_ok=True)

    # Format the date
    date_prefix = ""
    if isinstance(published_date, datetime):
        date_prefix = published_date.strftime("%Y%m%d-")

    # Sanitize the title
    clean_title = sanitize_filename(title)

    # Add suffix if provided
    if suffix:
        clean_title = f"{clean_title}_{suffix}"

    # Create the full filename
    filename = f"{date_prefix}{clean_title}.md"
    filepath = os.path.join(summaries_dir, filename)

    # Prepare the markdown content
    header = f"""# {title}

Author: {author}
Date: {published_date.strftime("%Y-%m-%d") if isinstance(published_date, datetime) else published_date}
Category: {category}
URL: {video_url}

> {description}

"""

    # Combine header and content
    full_content = header + content

    # Write to file
    with open(filepath, "w", encoding="utf-8") as file:
        file.write(full_content)

    return filepath
