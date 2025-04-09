import os


def get_processed_video_ids(skip_verification=False):
    """
    Get set of already processed video IDs from the index file.

    Args:
        skip_verification (bool): If True, return an empty set

    Returns:
        set: Set of processed video IDs or empty set if skip_verification is True
    """
    if skip_verification:
        return set()

    processed_video_ids = set()
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


def update_video_index(video_id, filepath, skip_verification=False):
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
