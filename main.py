import os
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

import google.generativeai as genai
import requests
from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi

# Load environment variables
load_dotenv()

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
) -> str:
    """
    Analyze transcript using Gemini API and return refined text.

    Args:
        transcript (str): Text transcript to analyze
        api_key (str): Gemini API key
        model_name (str): Gemini model name to use
        output_language (str): Desired output language
        chunk_size (int): Maximum chunk size for processing

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

        PROMPT_TEMPLATE = """
Turn the following unorganized text into a well-structured, readable format while retaining EVERY detail, context, and nuance of the original content.
Refine the text to improve clarity, grammar, and coherence WITHOUT cutting, summarizing, or omitting any information.
The goal is to make the content easier to read and process by:

- Organizing the content into logical sections with appropriate subheadings.
- Using bullet points or numbered lists where applicable to present facts, stats, or comparisons.
- Highlighting key terms, names, or headings with bold text for emphasis.
- Preserving the original tone, humor, and narrative style while ensuring readability.
- Adding clear separators or headings for topic shifts to improve navigation.
- Adding code examples in C# when it's possible

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


def get_videos_from_channel(channel_id: str, days:int = 8) -> list[tuple[str, str]]:
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
    documents_dir = os.path.join(os.path.expanduser("~"), "Documents/Summaries")
    index_file = os.path.join(documents_dir, "video_index.txt")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            processed_video_ids = {line.split(" | ")[0].strip() for line in f if line.strip()}
    
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
                    print(f"Video {item['snippet']['title']} was already processed. Skipping...")
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
    Save refined text to a markdown file and update the video index.
    File will be saved in the Documents/Summaries folder with format YYYYMMDD-title.md

    Args:
        title (str): YouTube video title
        video_url (str): YouTube video URL
        refined_text (str): Text to save

    Returns:
        str: Path to the saved file
    """
    try:
        # Determine the user's Documents folder
        documents_dir = os.path.join(os.path.expanduser("~"), "Documents")
        # Create Summaries directory inside Documents
        summaries_dir = os.path.join(documents_dir, "Summaries")
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
        # Update index file inside the Summaries directory in Documents
        index_file = os.path.join(summaries_dir, "video_index.txt")
        with open(index_file, "a", encoding="utf-8") as f:
            f.write(f"{video_id} | {filepath}\n")

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


# Example usage
try:
    # Get all recent videos
    nick_chapsas_id = "UCrkPsvLGln62OMZRO6K-llg"
    milan_jovanovic_id = "UCC_dVe-RI-vgCZfls06mDZQ"
    days = 15
    videos = get_videos_from_channel(nick_chapsas_id, days)
    videos.extend(get_videos_from_channel(milan_jovanovic_id, days))
    
    for video_url, video_title in videos:
        print(f"Processing video: {video_title}")
        
        # Get transcript
        transcript = get_youtube_transcript(video_url, language_code="en")
        
        # Analyze with Gemini
        api_key = os.getenv("GEMINI_API_KEY")
        refined_text = analyze_transcript_with_gemini(
            transcript=transcript,
            api_key=api_key,
            model_name="gemini-2.0-flash-thinking-exp-01-21",
            output_language="English")
        
        # Save to markdown file
        saved_file_path = save_to_markdown(video_title, video_url, refined_text)
        if saved_file_path:
            print(f"Saved to: {saved_file_path}")
            open_file(saved_file_path)

except Exception as e:
    print(f"Error: {str(e)}")