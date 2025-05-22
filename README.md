# YouTube to Markdown Converter

![YT2MD Logo](https://img.shields.io/badge/YT2MD-YouTube%20to%20Markdown-red)

YouTube to Markdown (YT2MD) is a powerful command-line tool that transforms YouTube video transcripts into well-structured, beautifully formatted markdown files. It leverages LLM technology to turn raw video transcripts into valuable, organized knowledge repositories.

📝 **Perfect for creating searchable notes from educational content**  
🧠 **Build your personal knowledge base from YouTube videos**  
🔍 **Automatically extract key concepts and structure from video content**  
🌐 **Support for multiple languages and translation**

## Why YT2MD?

YouTube contains vast amounts of valuable information, but video is not easily searchable, referenceable, or storable in knowledge management systems. YT2MD bridges this gap by:

1. **Automating transcript extraction** from YouTube videos
2. **Processing with LLMs** (both cloud and local) to structure raw transcripts
3. **Generating well-formatted markdown** with proper headings, lists, and code blocks
4. **Organizing content by categories and channels** for easy reference
5. **Supporting multiple LLM providers** (Gemini, Perplexity, Ollama) for flexibility

## Key Features

- **Category-Based Organization**: Process videos from specific knowledge categories
- **Channel Management**: Configure and track specific YouTube channels
- **Multiple LLM Support**: Process with cloud services (Gemini, Perplexity) or local models (Ollama)
- **Customizable Output**: Format markdown with language-specific enhancements
- **Video Filtering**: Process videos by date range or title keywords
- **Parallel Comparison**: Generate alternative markdown versions using different LLMs
- **Batch Processing**: Process multiple videos in a single command

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

## How It Works

YT2MD operates through a series of optimized steps:

1. **Video Collection**: Based on channels, categories, and date ranges
2. **Transcript Extraction**: Fetches transcripts via YouTube API
3. **LLM Strategy Selection**: Chooses the best LLM based on transcript length and language
4. **Content Processing**: 
   - Chunks long transcripts to optimize processing
   - Applies different prompts based on content category
   - Enhances structure while preserving all important information
5. **Metadata Enrichment**: Adds YAML frontmatter with video details
6. **Storage & Organization**: Files are saved with proper naming and categorization

Processing typically takes 1-3 minutes per video, depending on transcript length and LLM selection.

```
YouTube Video → Transcript → LLM Processing → Structured Markdown → Knowledge Base
```

## Output Format

YT2MD generates markdown files with:

- **YAML Frontmatter**: Title, source URL, author, publish date, description, category
- **Well-Structured Content**: 
  - Proper headings and subheadings
  - Bulleted and numbered lists
  - Code blocks with syntax highlighting
  - Emphasis on important concepts
  - Category-specific formatting (e.g., code examples for IT videos)

Example output (example):

```markdown
---
title: "Understanding Distributed Systems"
source: https://www.youtube.com/watch?v=example
author: "[[Nick Chapsas]]"
published: 2025-05-15
created: 2025-05-21
description: A comprehensive overview of distributed systems concepts and patterns
category: IT
length: 4230
tags: ["#Summaries/ToRead"]
---

# Understanding Distributed Systems

## Introduction to Distributed Computing

The speaker begins by explaining the fundamental principles that govern distributed systems:

- **Scalability**: Ability to handle growing amounts of work
- **Reliability**: Consistency of operations over time
- **Availability**: System uptime and accessibility

### CAP Theorem Explained

The CAP theorem states that distributed systems can only guarantee two out of three properties:

1. **Consistency**: All nodes see the same data at the same time
2. **Availability**: The system remains operational even with node failures
3. **Partition tolerance**: The system continues to operate despite network failures

## Implementation Patterns

...
```

## Use Cases

YT2MD is ideal for:

- **Personal Knowledge Management**: Create searchable notes from educational YouTube content
- **Research**: Extract structured information from video interviews and presentations
- **Content Creation**: Transform video content into article drafts or blog posts
- **Learning**: Convert technical talks into study materials
- **Documentation**: Create reference materials from tutorial videos
- **Multilingual Learning**: Process and translate content from other languages

## Advanced Configuration

YT2MD offers several configuration options for power users:

### LLM Strategy Configuration

The tool intelligently selects different LLM providers based on transcript length and category. This behavior can be customized in the configuration.

### Customizing Prompts

The system uses different prompts based on content category to optimize formatting. For example:
- IT videos get special treatment for code examples
- Crypto videos receive enhanced chart and price level formatting

### Performance Optimization

For long videos, the tool automatically splits transcripts into manageable chunks and processes them sequentially, maintaining context between segments.

## Roadmap

Upcoming features:

- Automatic image generation for key concepts
- Direct integration with note-taking apps (Obsidian, Logseq)
- Browser extension for one-click processing
- Support for automatic diagram generation 
- Batch scheduling and automatic processing

## Contributing

Contributions are welcome! Feel free to submit issues or pull requests.

## License

MIT
