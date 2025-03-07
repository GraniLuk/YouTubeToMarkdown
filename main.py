import argparse
import os
import os.path
import pickle
import re
import sys
from datetime import datetime, timedelta

import google.generativeai as genai
import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi

# Add this class near the top of the file, after imports


class Channel:
    def __init__(
        self, id: str, language_code: str, output_language: str, category: str
    ):
        self.id = id
        self.language_code = language_code
        self.output_language = output_language
        self.category = category


# Load environment variables
load_dotenv()


def get_script_dir() -> str:
    """
    Get the directory where the script is located
    """
    return os.path.dirname(os.path.abspath(__file__))


def get_youtube_transcript(video_url: str, language_code: str = "en") -> str:
    """
    Extract transcript from a YouTube video and return it as a string.

    Args:
        video_url (str): YouTube video URL
        language_code (str): Language code for the transcript (default: 'pl' for Polish)

    Returns:
        str: Video transcript as a single string
    """
    try:
        # Extract video ID from URL
        video_id = video_url.split("?v=")[1].split("&")[0]

        # Get transcript with specified language
        transcript_list = YouTubeTranscriptApi.get_transcript(
            video_id, languages=[language_code]
        )

        # Combine all transcript pieces into one string
        transcript = " ".join([transcript["text"] for transcript in transcript_list])

        return transcript

    except Exception as e:
        raise Exception(f"Transcript extraction error: {str(e)}")


def analyze_transcript_with_gemini(
    transcript: str,
    api_key: str,
    model_name: str = "gemini-1.5-pro",
    output_language: str = "English",
    chunk_size: int = 3000,
    category: str = "IT",
) -> str:
    """
    Analyze transcript using Gemini API and return refined text.

    Args:
        transcript (str): Text transcript to analyze
        api_key (str): Gemini API key
        model_name (str): Gemini model name to use
        output_language (str): Desired output language
        chunk_size (int): Maximum chunk size for processing
        category (str): Category of the content (default: 'IT')

    Returns:
        str: Refined and analyzed text
    """
    try:
        # Configure Gemini
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)

        # Split transcript into chunks if it's too long
        words = transcript.split()
        chunks = [
            " ".join(words[i : i + chunk_size])
            for i in range(0, len(words), chunk_size)
        ]

        # Process each chunk
        final_output = []
        previous_response = ""

        # Define category-specific bullet points
        category_prompts = {
            "IT": "- Adding code examples in C# when it's possible\n - Write diagram in mermaid syntax when it can help understand discussed subject\n - Add suitable tags at the beginning of the file, using 'Technical' as the main tag and adding subtags as needed. For example, '#Technical/Swagger #Technical/GraphQL",
            "Crypto": "- Adding TradingView chart links when price movements or technical analysis is discussed\n- Highlighting key price levels and market indicators mentioned\n- Including links to relevant blockchain explorers when specific transactions or contracts are discussed",
        }

        PROMPT_TEMPLATE = f"""
Turn the following unorganized text into a well-structured, readable format while retaining EVERY detail, context, and nuance of the original content.
Refine the text to improve clarity, grammar, and coherence WITHOUT cutting, summarizing, or omitting any information.
The goal is to make the content easier to read and process by:

- Organizing the content into logical sections with appropriate subheadings.
- Using bullet points or numbered lists where applicable to present facts, stats, or comparisons.
- Highlighting key terms, names, or headings with bold text for emphasis.
- Preserving the original tone, humor, and narrative style while ensuring readability.
- Adding clear separators or headings for topic shifts to improve navigation.
{category_prompts.get(category, "")}

Ensure the text remains informative, capturing the original intent, tone,
and details while presenting the information in a format optimized for analysis by both humans and AI.
REMEMBER that Details are important, DO NOT overlook Any details, even small ones.
All output must be generated entirely in [Language]. Do not use any other language at any point in the response.
Text:
"""

        for i, chunk in enumerate(chunks):
            # Prepare prompt with context if needed
            if previous_response:
                context_prompt = (
                    "The following text is a continuation... "
                    f"Previous response:\n{previous_response}\n\nNew text to process(Do Not Repeat the Previous response:):\n"
                )
            else:
                context_prompt = ""

            # Create full prompt
            formatted_prompt = PROMPT_TEMPLATE.replace("[Language]", output_language)
            full_prompt = f"{context_prompt}{formatted_prompt}\n\n{chunk}"

            # Generate response
            response = model.generate_content(full_prompt)
            previous_response = response.text
            final_output.append(response.text)

        # Combine all responses
        return "\n\n".join(final_output)

    except Exception as e:
        raise Exception(f"Gemini processing error: {str(e)}")


def get_video_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"


def get_videos_from_channel(channel_id: str, days: int = 8) -> list[tuple[str, str]]:
    """
    Get all unprocessed videos from a YouTube channel published in the last days.
    Checks against video_index.txt to skip already processed videos.

    Args:
        channel_id (str): YouTube channel ID

    Returns:
        list[tuple[str, str]]: A list of tuples containing (video_url, video_title) for unprocessed videos
    """
    API_KEY = os.getenv("YOUTUBE_API_KEY")

    # Get processed video IDs from index file
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

    # Calculate the datetime 24 hours ago
    end_date = datetime.now()
    start_date = (end_date - timedelta(days=days)).isoformat("T") + "Z"

    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={channel_id}&type=video&order=date&publishedAfter={start_date}&key={API_KEY}&maxResults=50"

    videos = []
    next_page_token = None

    while True:
        if next_page_token:
            current_url = f"{url}&pageToken={next_page_token}"
        else:
            current_url = url

        response = requests.get(current_url)
        data = response.json()

        if "items" in data:
            for item in data["items"]:
                video_id = item["id"]["videoId"]
                if video_id in processed_video_ids:
                    print(
                        f"Video {item['snippet']['title']} was already processed. Skipping..."
                    )
                    continue

                video_url = f"https://www.youtube.com/watch?v={video_id}"
                title = item["snippet"]["title"]
                videos.append((video_url, title))

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break
    return videos


def save_to_markdown(title: str, video_url: str, refined_text: str) -> str:
    """
    Save refined text to a markdown file, update the video index, and upload to Google Drive.
    File will be saved in the path specified in SUMMARIES_PATH environment variable

    Args:
        title (str): YouTube video title
        video_url (str): YouTube video URL
        refined_text (str): Text to save

    Returns:
        str: Path to the saved file
    """
    try:
        # Get path from environment variable
        summaries_dir = os.getenv("SUMMARIES_PATH")
        if not summaries_dir:
            raise ValueError("SUMMARIES_PATH environment variable is not set")

        # Create directory if it doesn't exist
        os.makedirs(summaries_dir, exist_ok=True)

        # Clean the title to make it filesystem-friendly
        title = re.sub(r"[^\w\s-]", "", title)
        title = title.replace(" ", "_")

        # Add date prefix to filename
        today = datetime.now().strftime("%Y%m%d")
        filename = f"{today}-{title}.md"

        # Create full path
        filepath = os.path.join(summaries_dir, filename)

        # Save to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# YouTube Video\n\n")
            f.write(f"Source: {video_url}\n\n")
            f.write(refined_text)

        # Extract video ID from URL
        video_id = video_url.split("?v=")[1].split("&")[0]
        # Update index file inside the summaries directory
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


def setup_google_drive():
    """
    Sets up Google Drive API credentials
    Returns:
        Google Drive API service
    """
    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    creds = None
    script_dir = get_script_dir()
    token_path = os.path.join(script_dir, "token.pickle")
    credentials_path = os.path.join(script_dir, "credentials.json")

    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                os.remove(token_path)
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=8080)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(
                port=8080, access_type="offline", include_granted_scopes="true"
            )
        # Save the credentials for the next run
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)

    return build("drive", "v3", credentials=creds)


def upload_to_drive(service, file_path: str, folder_id: str = None) -> str:
    """
    Upload a file to Google Drive

    Args:
        service: Google Drive API service instance
        file_path (str): Path to the file to upload
        folder_id (str): Optional Google Drive folder ID

    Returns:
        str: ID of the uploaded file
    """
    file_metadata = {
        "name": os.path.basename(file_path),
        "parents": [folder_id] if folder_id else [],
    }

    media = MediaFileUpload(file_path, mimetype="text/markdown", resumable=True)

    file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )

    return file.get("id")


def main():
    parser = argparse.ArgumentParser(
        description="Process YouTube videos and create markdown summaries"
    )
    parser.add_argument(
        "--days", type=int, default=3, help="Number of days to look back for videos"
    )
    parser.add_argument(
        "--category",
        type=str,
        default="IT",
        choices=["IT", "Crypto", "AI"],
        help="Category of channels to process (IT, Crypto, or AI)",
    )
    args = parser.parse_args()

    try:
        # Define channels with their language settings and categories
        all_channels = [
            # IT Channels
            Channel("UCrkPsvLGln62OMZRO6K-llg", "en", "English", "IT"),  # Nick Chapsas
            Channel(
                "UCC_dVe-RI-vgCZfls06mDZQ", "en", "English", "IT"
            ),  # Milan Jovanovic
            Channel("UCidgSn6WJ9Fv3kwUtoI7_Jg", "en", "English", "IT"),  # Stefan Dokic
            Channel("UCX189tVw5L1E0uRpzJgj8mQ", "pl", "Polish", "IT"),  # DevMentors
            # Crypto Channels - Add your crypto channels here
            # Channel("UCBIt1VN5j37PVM8LLSuTTlw", "en", "English", "Crypto"),  # Coin Bureau
            # Channel("UCqK_GSMbpiV8spgD3ZGloSw", "en", "English", "Crypto"),  # Crypto Banter
            Channel("UCsaWU2rEXFkufFN_43jH2MA", "pl", "Polish", "Crypto"),  # Jarzombek
            Channel("UCXasJkcS9vY8X4HgzReo10A", "pl", "Polish", "Crypto"),  # Ostapowicz
            Channel(
                "UCKy4pRGNqVvpI6HrO9lo3XA", "pl", "Polish", "Crypto"
            ),  # Krypto Raport
            Channel("UCWTpgi3bE5gIVfhEys-T12A", "pl", "Polish", "AI"), # Mike Tomala
            # Add more crypto channels as needed
        ]

        # Filter channels based on selected category
        channels = [
            channel for channel in all_channels if channel.category == args.category
        ]

        if not channels:
            print(f"No channels found for category: {args.category}")
            return

        print(f"Processing {args.category} channels...")

        videos = []
        for channel in channels:
            channel_videos = get_videos_from_channel(channel.id, args.days)
            videos.extend([(url, title, channel) for url, title in channel_videos])

        for video_url, video_title, channel in videos:
            print(f"Processing video: {video_title}")

            # Get transcript with channel-specific language
            transcript = get_youtube_transcript(
                video_url, language_code=channel.language_code
            )

            # Analyze with Gemini using channel-specific output language
            api_key = os.getenv("GEMINI_API_KEY")
            refined_text = analyze_transcript_with_gemini(
                transcript=transcript,
                api_key=api_key,
                model_name="gemini-2.0-pro-exp-02-05",
                output_language=channel.output_language,
                category=channel.category,
            )

            # Save to markdown file
            saved_file_path = save_to_markdown(video_title, video_url, refined_text)
            if saved_file_path:
                print(f"Saved to: {saved_file_path}")
                open_file(saved_file_path)

    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    main()
