import os
import re
import sys
import unicodedata
from datetime import datetime

import yaml

from yt2md.logger import get_logger
from yt2md.video_index import update_video_index

# Get logger for this module
logger = get_logger("file_operations")


def get_script_dir():
    """Get the directory where the script is running from."""
    # If packaged with PyInstaller, use the _MEIPASS attribute
    if hasattr(sys, "_MEIPASS"):
        return getattr(sys, "_MEIPASS")
    # Otherwise, use the directory of the script
    return os.path.abspath(os.path.dirname(__file__))


def sanitize_filename(filename: str) -> str:
    """Clean up a filename to make it valid for all platforms."""
    logger.debug(f"Sanitizing filename: {filename[:50]}...")
    original_filename = filename

    # Remove emojis and other special unicode characters
    try:
        # Try to normalize and remove non-ASCII characters
        filename = unicodedata.normalize("NFKD", filename)
        # Remove remaining non-ASCII characters
        filename = "".join(c for c in filename if ord(c) < 128)
    except Exception as e:
        logger.warning(f"Unicode normalization failed: {str(e)}")
        # Fallback for any unicode errors
        filename = re.sub(r"[^\x00-\x7F]+", "", filename)

    # Replace invalid characters with underscores
    filename = re.sub(r'[\\/:*?"<>|#]', "_", filename)
    # Remove multiple spaces and replace with single space
    filename = re.sub(r"\s+", " ", filename)
    # Trim spaces from the beginning and end
    filename = filename.strip()
    # Limit filename length to prevent issues
    if len(filename) > 200:
        filename = filename[:197] + "..."
        logger.debug("Filename truncated due to length")
    # Ensure filename isn't empty after sanitizing
    if not filename or filename.isspace():
        filename = "untitled_content"
        logger.warning("Empty filename after sanitization, using default")

    if filename != original_filename:
        logger.debug(f"Sanitized filename: {filename[:50]}...")

    return filename


def open_file(filepath: str) -> bool:
    """Open a file with the default system application."""
    try:
        logger.info(f"Opening file: {filepath}")
        # Open file with default application
        os.startfile(filepath)
        return True
    except Exception as e:
        logger.error(f"Error opening file {filepath}: {e}")
        return False


def _is_same_video_file(filepath: str, video_url: str) -> bool:
    """Check if existing file belongs to the same video by comparing frontmatter source or video ID."""
    if not os.path.exists(filepath):
        return False

    target_vid = None
    try:
        from yt2md.youtube import extract_video_id
        target_vid = extract_video_id(video_url)
    except Exception:
        pass

    try:
        # Read header only (first 40 lines)
        header_lines = []
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for _ in range(40):
                line = f.readline()
                if not line:
                    break
                header_lines.append(line)
        header_text = "".join(header_lines)

        source_match = re.search(
            r"^source:\s*['\"]?(https?://[^\s'\"]+)", header_text, re.MULTILINE
        )
        if source_match:
            existing_source = source_match.group(1).strip().rstrip("'\"")
            if existing_source == video_url:
                return True
            if target_vid:
                try:
                    from yt2md.youtube import extract_video_id
                    existing_vid = extract_video_id(existing_source)
                    if existing_vid and existing_vid == target_vid:
                        return True
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Could not read existing file header from {filepath}: {e}")

    return False


def save_to_markdown(
    title: str,
    video_url: str,
    content: str,
    author: str,
    published_date: str,
    description: str,
    category: str,
    suffix: str = "",
    skip_verification: bool = False,
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
        skip_verification: If True, don't update the index file

    Returns:
        str: Path to the saved file
    """
    logger.debug(f"Saving markdown for: {title}")
    logger.debug(
        f"Content length: {len(content)} characters, Author: {author}, Category: {category}"
    )

    # Get path from environment variable
    summaries_dir = os.getenv("SUMMARIES_PATH")
    if not summaries_dir:
        logger.error("SUMMARIES_PATH environment variable is not set")
        raise ValueError("SUMMARIES_PATH environment variable is not set")

    # Create nested directory structure
    if category:
        # Clean up author name to make it filesystem-friendly
        clean_author = re.sub(r"[^\w\s-]", "", author)
        clean_author = clean_author.replace(" ", "_")
        # Create path with category and channel subfolders
        file_dir = os.path.join(summaries_dir, category, clean_author)
        logger.debug(f"Using categorized directory: {file_dir}")
    else:
        # Fallback to main directory if no category
        file_dir = summaries_dir
        logger.debug(f"Using main summaries directory: {file_dir}")

    # Make sure the directory exists
    try:
        os.makedirs(file_dir, exist_ok=True)
        logger.debug(f"Ensured directory exists: {file_dir}")
    except Exception as e:
        logger.error(f"Failed to create directory {file_dir}: {str(e)}")
        raise

    clean_base = sanitize_filename(title)
    clean_suffix = sanitize_model_name_for_suffix(suffix) if suffix else ""

    try:
        from yt2md.youtube import extract_video_id
        video_id = extract_video_id(video_url)
    except Exception:
        video_id = None

    if clean_suffix:
        filename = f"{clean_base}_{clean_suffix}.md"
    else:
        filename = f"{clean_base}.md"

    filepath = os.path.join(file_dir, filename)

    # Check for naming collisions with DIFFERENT videos
    if os.path.exists(filepath) and not _is_same_video_file(filepath, video_url):
        logger.warning(
            f"File '{filename}' already exists for a different video. Disambiguating filename to prevent overwrite."
        )
        disambiguated = False
        if video_id and video_id not in clean_base:
            id_filename = (
                f"{clean_base}_{video_id}_{clean_suffix}.md"
                if clean_suffix
                else f"{clean_base}_{video_id}.md"
            )
            id_path = os.path.join(file_dir, id_filename)
            if not os.path.exists(id_path) or _is_same_video_file(id_path, video_url):
                filename = id_filename
                filepath = id_path
                disambiguated = True

        if not disambiguated:
            counter = 2
            suffix_part = f"_{clean_suffix}" if clean_suffix else ""
            id_part = f"_{video_id}" if (video_id and video_id not in clean_base) else ""
            while os.path.exists(filepath) and not _is_same_video_file(filepath, video_url):
                filename = f"{clean_base}{id_part} ({counter}){suffix_part}.md"
                filepath = os.path.join(file_dir, filename)
                counter += 1

        logger.info(f"Using disambiguated file path: {filepath}")

    logger.debug(f"Writing to file: {filepath}")

    # Get current date for 'created' field
    created_date = datetime.now().strftime("%Y-%m-%d")

    # Prepare the markdown content using safe YAML serialization to handle special characters
    metadata = {
        "title": title,
        "source": video_url,
        "author": f"[[{author}]]",
        "published": published_date,
        "created": created_date,
        "description": description or "",
        "category": category,
        "length": len(content.split()),
        "tags": ["#Summaries/ToRead"],
    }

    header_yaml = yaml.safe_dump(
        metadata, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).strip()
    header = f"---\n{header_yaml}\n---\n\n"

    # Combine header and content
    full_content = header + content

    # Write to file
    try:
        with open(filepath, "w", encoding="utf-8") as file:
            file.write(full_content)
        logger.debug(f"Successfully wrote {len(full_content)} characters to file")
    except Exception as e:
        logger.error(f"Failed to write to file {filepath}: {str(e)}")
        raise

    try:
        # Extract video ID from URL
        from yt2md.youtube import extract_video_id
        video_id = extract_video_id(video_url)
        if video_id:
            logger.debug(f"Extracted video ID: {video_id}")
            # Update index file inside the main summaries directory
            update_video_index(video_id, filepath, skip_verification)
            logger.debug("Updated video index")
        else:
            logger.warning(f"Could not extract video ID from URL: {video_url}")
    except Exception as e:
        logger.error(f"Error updating video index: {str(e)}")

    return filepath


def sanitize_model_name_for_suffix(model_name: str) -> str:
    """
    Sanitize a model name to create a valid filename suffix.

    Args:
        model_name: The original model name

    Returns:
        str: A sanitized suffix suitable for filenames
    """
    if not model_name:
        return "model"

    # Remove version/tag part after colon
    model_name = model_name.split(":")[0]

    # For HuggingFace models like "hf.co/unsloth/DeepSeek-R1-0528-Qwen3-8B-GGUF"
    # Extract the actual model name part
    if "/" in model_name:
        # Take the last part after the last slash
        model_name = model_name.split("/")[-1]

    # Replace invalid characters with underscores or remove them
    model_name = re.sub(r'[\\/:*?"<>|#.]', "_", model_name)

    # Remove multiple underscores and replace with single
    model_name = re.sub(r"_+", "_", model_name)

    # Remove leading/trailing underscores
    model_name = model_name.strip("_")

    # Limit length to keep filename reasonable
    if len(model_name) > 30:
        model_name = model_name[:30]

    # Ensure we have something valid
    if not model_name or model_name.isspace():
        model_name = "model"

    return model_name
