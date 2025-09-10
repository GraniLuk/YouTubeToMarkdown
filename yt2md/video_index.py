import os


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
    summaries_dir = os.getenv("SUMMARIES_PATH")
    if not summaries_dir:
        raise ValueError("SUMMARIES_PATH environment variable is not set")

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

    summaries_dir = os.getenv("SUMMARIES_PATH")
    if not summaries_dir:
        raise ValueError("SUMMARIES_PATH environment variable is not set")

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
    summaries_dir = os.getenv("SUMMARIES_PATH")
    if not summaries_dir:
        raise ValueError("SUMMARIES_PATH environment variable is not set")
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

