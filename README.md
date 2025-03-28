# YouTube to Markdown Converter

A tool to automatically convert YouTube video transcripts into well-formatted markdown files.

## Installation

1. Clone this repository
2. Install the package in development mode:
```bash
pip install -e .
```

## Usage

After installation, you can use the `yt2md` command from anywhere:

```bash
# Process videos from channels in a category
yt2md --category IT --days 7

# Process a single video
yt2md --url "https://www.youtube.com/watch?v=..."
```

Make sure to set up your environment variables in a .env file:
- GEMINI_API_KEY
- YOUTUBE_API_KEY
- SUMMARIES_PATH
- GOOGLE_DRIVE_FOLDER_ID (optional)

## Channel Configuration

The `channels.yaml` file in the `config` directory organizes YouTube channels into categories. Each channel entry requires:
- `id`: The YouTube channel ID (found in channel URL)
- `name`: Display name for the channel
- `language_code`: Source language code (e.g., 'en' for English, 'pl' for Polish)
- `output_language`: Target language for the output

Example configuration:
```yaml
IT:
  - id: UCrkPsvLGln62OMZRO6K-llg
    name: Nick Chapsas
    language_code: en
    output_language: English
    
AI:
  - id: UCWTpgi3bE5gIVfhEys-T12A
    name: Mike Tomala
    language_code: pl
    output_language: Polish
```

# YouTube Playlist Processor using Gemini API
<br>
<br>
✅ Added Language Support, now the output file is in the language of user's input.(might not be as good as english, test it yourself!)<br>
✅ Added single video url support, no need to put it in a playlist.

<br>
<br>
This Python application extracts transcripts from YouTube playlists and refines them using the Google Gemini API(which is free). It takes a YouTube playlist URL as input, extracts transcripts for each video, and then uses Gemini to reformat and improve the readability of the combined transcript. The output is saved as a text file.
<br><br>
So you can have a neatly formatted book out of a YouTube playlist!
I personally use it to convert large YouTube playlists containing dozens of long videos into a very large organized markdown file to give it as input to NotebookLM as one source.<br><br>

<br><br>

*   Batch processing of entire playlists
*   Refine transcripts using Google Gemini API for improved formatting and readability.
*   User-friendly PyQt5 graphical interface.
*   Selectable Gemini models.
*   Output to markdown file.
<br><br><br><br>

## Features
- 🎥 Automatic transcript extraction from YouTube playlists
- 🧠 AI-powered text refinement using Gemini models
- 📁 Configurable output file paths
- ⏳ Progress tracking for both extraction and refinement
- 📄 Output to formatted markdown file.

## Requirements
- Python 3.9+
- Google Gemini API key
- YouTube playlist URL

## Installation
```bash
pip install -r requirements.txt
```
## How does it work?
* First, the transcript of every video in the playlist is fetched.
* since gemini api doesnt have unlimited context window for input and output, the text for each video gets divided into chunks(right now, chunk size is set to 3000 after testing, but it can be changed)
* Each text chunk is then sent to the Gemini API, along with a context prompt that includes the previously refined text. This helps maintain consistency and coherence across chunks.
* The refined output from Gemini for each chunk is appended to the final output file.
* This process is repeated for every video in the playlist, resulting in a single, refined transcript output file for the entire playlist.
    
## Usage

1.  **Get a Gemini API Key:** You need a Google Gemini API key. Obtain one from [Google AI Studio](https://ai.google.dev/gemini-api/docs/api-key).
2.  **Run the Application:**
    ```bash
    python main.py
    ```


> YouTube playlist used for example files : https://www.youtube.com/playlist?list=PLmHVyfmcRKyx1KSoobwukzf1Nf-Y97Rw0
