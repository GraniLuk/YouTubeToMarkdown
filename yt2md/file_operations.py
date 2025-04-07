import os
import os.path
import re
from datetime import datetime

from yt2md.google_drive import setup_google_drive, upload_to_drive


def get_script_dir() -> str:
    """
    Get the directory where the script is located
    """
    return os.path.dirname(os.path.abspath(__file__))


def save_to_markdown(
    title: str,
    video_url: str,
    refined_text: str,
    author: str,
    published_date: str,
    description: str,
    category: str = None,
) -> str:
    """
    Save refined text to a markdown file, update the video index, and upload to Google Drive.
    File will be saved in a nested structure: SUMMARIES_PATH/category/author

    Args:
        title (str): YouTube video title
        video_url (str): YouTube video URL
        refined_text (str): Text to save
        author (str): Author of the video
        published_date (str): Published date of the video
        description (str): Description of the video
        category (str): Category of the video (IT, Crypto, AI, etc.)

    Returns:
        str: Path to the saved file
    """
    try:
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

        # Create directory structure if it doesn't exist
        os.makedirs(file_dir, exist_ok=True)

        # Clean the title to make it filesystem-friendly
        filenameTitle = re.sub(
            r'[\\/*?:"<>|]', "", title
        )  # Remove characters not allowed in Windows filenames
        filenameTitle = re.sub(
            r"[^\w\s.-]", "", filenameTitle
        )  # Remove other non-alphanumeric chars except dots and dashes
        filenameTitle = filenameTitle.replace(" ", "_")
        # Limit filename length to avoid path length issues
        filenameTitle = (
            filenameTitle[:150] if len(filenameTitle) > 150 else filenameTitle
        )

        filename = f"{filenameTitle}.md"

        # Create full path
        filepath = os.path.join(file_dir, filename)

        # Get current date for 'created' field
        created_date = datetime.now().strftime("%Y-%m-%d")

        # Create the frontmatter
        frontmatter = f"""---
title: "{title}"
source: {video_url}
author: "[[{author}]]"
published: {published_date}
created: {created_date}
description: {description}
tags:
---

"""
        # Save to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter)
            f.write(refined_text)

        # Extract video ID from URL
        video_id = video_url.split("?v=")[1].split("&")[0]
        # Update index file inside the main summaries directory
        index_file = os.path.join(summaries_dir, "video_index.txt")
        with open(index_file, "a", encoding="utf-8") as f:
            f.write(f"{video_id} | {filepath}\n")

        # After saving the file locally, upload to Google Drive
        try:
            drive_service = setup_google_drive()
            YOUTUBE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

            file_id = upload_to_drive(drive_service, filepath, YOUTUBE_FOLDER_ID)
            print(f"Uploaded to Google Drive with ID: {file_id}")
        except Exception as e:
            print(f"Warning: Failed to upload to Google Drive: {str(e)}")

        return os.path.abspath(filepath)

    except Exception as e:
        raise Exception(f"Error saving to markdown: {str(e)}")


def open_file(filepath: str):
    """
    Open a file using the default application on Windows.
    """
    try:
        os.startfile(filepath)
    except Exception as e:
        print(f"Failed to open file {filepath}: {str(e)}")
