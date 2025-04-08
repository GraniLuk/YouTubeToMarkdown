import os
import re
import sys
from datetime import datetime


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
    # Get path from environment variable
    summaries_dir = os.getenv("SUMMARIES_PATH")
    if not summaries_dir:
        raise ValueError("SUMMARIES_PATH environment variable is not set")
    
    # Create nested directory structure
    if category:
        # Clean up author name to make it filesystem-friendly
        clean_author = re.sub(r"[^\w\s-]", "", author)
        clean_author = clean_author.replace(" ", "_")
        # Create path with category and channel subfolders
        file_dir = os.path.join(summaries_dir, category, clean_author)
    else:
        # Fallback to main directory if no category
        file_dir = summaries_dir

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
    filepath = os.path.join(file_dir, filename)

    # Get current date for 'created' field
    created_date = datetime.now().strftime("%Y-%m-%d")

    # Prepare the markdown content
    header = f"""---
 title: "{title}"
 source: {video_url}
 author: "[[{author}]]"
 published: {published_date}
 created: {created_date}
 description: {description}
 tags:
 ---

"""

    # Combine header and content
    full_content = header + content

    # Write to file
    with open(filepath, "w", encoding="utf-8") as file:
        file.write(full_content)

    return filepath
