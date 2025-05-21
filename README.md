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

# Collect more videos per channel (default is 10)
yt2md --category AI --max-videos 30
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

   ```text
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

### Fetching More Videos

By default, the tool collects up to 10 videos per channel. To retrieve more videos:

```bash
yt2md --category IT --max-videos 30
```

The tool automatically paginates through all available YouTube API results until it reaches the maximum number of videos specified by `--max-videos` or until all available videos within the specified time frame have been retrieved.

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
