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

# Process videos with Ollama (local LLM)
yt2md --category IT --days 3 --ollama

# Process videos with cloud services only
yt2md --category IT --days 3 --cloud

# Skip verification of already processed videos and don't update index
yt2md --url "https://www.youtube.com/watch?v=..." --skip-verification

# Process videos from a specific channel
yt2md --category IT --channel "Nick Chapsas" --days 7
```

You can also filter videos by title for specific channels by adding `title_filters` to the channel configuration in `channels.yaml`. See the Channel Configuration section below for details.

Make sure to set up your environment variables in a .env file:
- GEMINI_API_KEY
- YOUTUBE_API_KEY
- SUMMARIES_PATH
- GOOGLE_DRIVE_FOLDER_ID (optional)
- PERPLEXITY_API_KEY (optional, used as fallback for rate limits)

### Using Ollama

To use [Ollama](https://ollama.ai/) (local LLM) for processing videos:

1. Install Ollama on your system from [ollama.ai](https://ollama.ai/)
2. Add the following environment variables to your .env file:
   ```
   OLLAMA_MODEL=gemma3:4b  # or any model you have pulled
   OLLAMA_BASE_URL=http://localhost:11434  # default, change if running on another host/port
   ```
3. Run the tool with the `--ollama` flag:
   ```bash
   yt2md --url "https://www.youtube.com/watch?v=..." --ollama
   ```

This will process the video with both cloud and local LLMs, generating two separate markdown files for comparison. Each file will be suffixed with the model name used (e.g., "Title_gemini.md" and "Title_gemma3.md").

### Using Cloud Services Only

Use the `--cloud` flag when you want to:
- Force using only cloud services (Gemini or Perplexity) regardless of transcript length
- Skip local LLM processing completely, even for short transcripts

```bash
yt2md --url "https://www.youtube.com/watch?v=..." --cloud
```

This parameter takes precedence over the `--ollama` parameter, so if both are specified, only cloud processing will be used.

### Skip Verification

Use the `--skip-verification` flag when you want to:
- Process a video that has already been processed before
- Skip adding entries to the video index file
- Generate multiple summaries of the same video with different parameters

```bash
yt2md --url "https://www.youtube.com/watch?v=..." --skip-verification
```

## Channel Configuration

The `channels.yaml` file in the `config` directory organizes YouTube channels into categories. Each channel entry requires:
- `id`: The YouTube channel ID (found in channel URL)
- `name`: Display name for the channel
- `language_code`: Source language code (e.g., 'en' for English, 'pl' for Polish)
- `output_language`: Target language for the output

Optional configuration:
- `title_filters`: List of strings to filter videos by title (only process videos containing at least one of these strings)

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
    
  # Example with title filters - only process videos with "AI", "GPT", or "LLM" in title
  - id: UCnz-ZXXER4jOvuED5trXfEA
    name: TechLead
    language_code: en
    output_language: English
    title_filters:
      - "AI"
      - "GPT"
      - "LLM"
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
