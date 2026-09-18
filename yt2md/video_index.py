import os


def _get_summaries_dir() -> str:
    """Get SUMMARIES_PATH from environment, loading .env if needed."""
    summaries_dir = os.getenv("SUMMARIES_PATH")
    if not summaries_dir:
        from dotenv import load_dotenv
        for env_cand in [
            os.path.abspath(os.path.join(os.path.dirname(__file__), ".env")),
            os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")),
        ]:
            if os.path.exists(env_cand):
                load_dotenv(env_cand)
                break
        summaries_dir = os.getenv("SUMMARIES_PATH")

    if not summaries_dir:
        raise ValueError("SUMMARIES_PATH environment variable is not set")
    return summaries_dir


def get_processed_video_ids(skip_verification: bool = False) -> set[str]:
    """
    Get set of already processed video IDs from the index file.

    Args:
        skip_verification (bool): If True, return an empty set

    Returns:
        set: Set of processed video IDs or empty set if skip_verification is True
    """
    if skip_verification:
        return set()

    processed_video_ids = set[str]()
    summaries_dir = _get_summaries_dir()

    index_file = os.path.join(summaries_dir, "video_index.txt")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            processed_video_ids = {
                line.split(" | ")[0].strip() for line in f if line.strip()
            }

    return processed_video_ids


def update_video_index(
    video_id: str, filepath: str, skip_verification: bool = False
) -> bool:
    """
    Update the video index with new processed video.

    Args:
        video_id (str): YouTube video ID
        filepath (str): Path to the saved markdown file
        skip_verification (bool): If True, don't update the index

    Returns:
        bool: True if index was updated, False otherwise
    """
    if skip_verification:
        return False

    summaries_dir = _get_summaries_dir()

    # Create index directory if it doesn't exist
    os.makedirs(summaries_dir, exist_ok=True)

    try:
        # Update index file inside the main summaries directory
        index_file = os.path.join(summaries_dir, "video_index.txt")
        with open(index_file, "a", encoding="utf-8") as f:
            f.write(f"{video_id} | {filepath}\n")
        return True
    except Exception as e:
        print(f"Warning: Could not update video index: {e}")
        return False


def find_markdown_files_for_video(video_id: str) -> list[str]:
    """Return list of existing markdown file paths for a given processed video id.

    Skips status marker entries (like VIDEO_UNAVAILABLE) and only returns paths that
    currently exist on disk and end with .md.
    """
    summaries_dir = _get_summaries_dir()
    index_file = os.path.join(summaries_dir, "video_index.txt")
    paths: list[str] = []
    if not os.path.exists(index_file):
        return paths
    try:
        with open(index_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                parts = line.split(" | ", 1)
                if len(parts) != 2:
                    continue
                vid, path = parts[0].strip(), parts[1].strip()
                if vid == video_id and path.lower().endswith('.md') and os.path.isfile(path):
                    paths.append(path)
    except Exception:
        pass
    return paths


def is_video_already_processed_by_title_author(
    title: str, author: str, skip_verification: bool = False
) -> bool:
    """
    Check if a video has already been processed by matching title and author.
    This helps detect duplicates when Instagram returns different shortcodes for the same reel.

    Args:
        title (str): Video title to search for
        author (str): Video author/channel name to search for
        skip_verification (bool): If True, return False (don't verify)

    Returns:
        bool: True if a file with matching title and author exists, False otherwise
    """
    if skip_verification:
        return False

    if not title or not author:
        return False

    summaries_dir = os.getenv("SUMMARIES_PATH")
    if not summaries_dir:
        from dotenv import load_dotenv

        env_cand = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
        if os.path.exists(env_cand):
            load_dotenv(env_cand)
        summaries_dir = os.getenv("SUMMARIES_PATH")

    if not summaries_dir:
        return False

    try:
        import yaml

        # Recursively search for markdown files in summaries directory
        for root, dirs, files in os.walk(summaries_dir):
            # Skip the top-level directory if it contains video_index.txt (avoid non-category files)
            if root == summaries_dir:
                # Only look in subdirectories (categories)
                continue

            for filename in files:
                if not filename.endswith(".md"):
                    continue

                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                        # Extract YAML frontmatter
                        if content.startswith("---"):
                            end_idx = content.find("---", 3)
                            if end_idx != -1:
                                yaml_content = content[3:end_idx]
                                metadata = yaml.safe_load(yaml_content)
                                if metadata:
                                    existing_title = metadata.get("title", "").strip()
                                    existing_author = metadata.get("author", "").strip()
                                    # Remove [[]] brackets if present in author field
                                    existing_author = (
                                        existing_author.replace("[[", "")
                                        .replace("]]", "")
                                        .strip()
                                    )

                                    # Normalize for comparison (remove special characters, lowercase)
                                    norm_title = _normalize_for_comparison(existing_title)
                                    norm_search_title = _normalize_for_comparison(title)
                                    norm_author = _normalize_for_comparison(existing_author)
                                    norm_search_author = _normalize_for_comparison(author)

                                    # Match if both title and author are similar
                                    if (
                                        norm_title
                                        and norm_search_title
                                        and norm_title == norm_search_title
                                        and norm_author
                                        and norm_search_author
                                        and norm_author == norm_search_author
                                    ):
                                        return True
                except Exception:
                    pass
    except Exception:
        pass

    return False


def _normalize_for_comparison(text: str) -> str:
    """Normalize text for comparison by removing special chars and extra whitespace."""
    import re

    if not text:
        return ""
    # Remove special characters and multiple spaces, convert to lowercase
    normalized = re.sub(r"[^\w\s]", "", text)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.lower().strip()

