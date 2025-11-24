# Audio Fallback Feature

## Overview

The audio fallback feature provides an alternative transcript extraction method when `youtube-transcript-api` fails or gets blocked. It uses `yt-dlp` to download audio and `Whisper` for speech-to-text transcription.

## When Fallback Activates

The fallback system automatically activates in these situations:

1. **No Transcript Available** - Video has no transcript or captions
2. **Transcripts Disabled** - Channel has disabled transcripts
3. **Video Unavailable** - Video is region-locked or restricted
4. **IP Blocked** - YouTube blocks your IP (common on cloud providers)
5. **Consecutive Failures** - After 3 consecutive failures (configurable)

## Prerequisites

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `yt-dlp` - YouTube downloader
- `openai-whisper` - Local speech-to-text model
- `torch` - Required by Whisper
- `ffmpeg-python` - Audio format conversion

### 2. Install FFmpeg

**Windows:**
```powershell
# Using Chocolatey
choco install ffmpeg

# Or download from: https://ffmpeg.org/download.html
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg  # Debian/Ubuntu
sudo yum install ffmpeg  # CentOS/RHEL
```

### 3. Download Whisper Model

**IMPORTANT:** You must pre-download the Whisper model before using the fallback feature.

```bash
# Download the base model (recommended, ~150MB)
whisper --model base --language English dummy.mp3

# Or download other models:
whisper --model tiny --language English dummy.mp3    # Fastest (~75MB)
whisper --model small --language English dummy.mp3   # Better accuracy (~500MB)
whisper --model medium --language English dummy.mp3  # High accuracy (~1.5GB)
whisper --model large --language English dummy.mp3   # Best accuracy (~3GB)
```

**Note:** Create a dummy audio file first if you don't have one:
```bash
# On Windows (PowerShell)
"test" | Out-File -Encoding ascii dummy.mp3

# On Linux/macOS
echo "test" > dummy.mp3
```

## Configuration

Add these settings to your `.env` file (see `.env.example`):

```bash
# Enable audio fallback (default: true)
ENABLE_AUDIO_FALLBACK=true

# Whisper model: tiny, base, small, medium, large (default: base)
WHISPER_MODEL=base

# Device: cpu or cuda (default: cpu)
# Set to 'cuda' if you have an NVIDIA GPU with CUDA installed
WHISPER_DEVICE=cpu

# Temporary audio cache directory (default: temp_audio)
AUDIO_CACHE_DIR=temp_audio

# Maximum audio file size in MB (default: 100)
MAX_AUDIO_SIZE_MB=100

# Minimum video duration for audio fallback in seconds (default: 30)
# Videos shorter than this will skip audio fallback processing
MIN_VIDEO_DURATION_SECONDS=30

# Consecutive failures before switching to fallback-only mode (default: 3)
CONSECUTIVE_FAILURES_THRESHOLD=3
```

## Model Selection Guide

| Model  | Size   | Speed      | Accuracy | Use Case |
|--------|--------|------------|----------|----------|
| tiny   | ~75MB  | Very Fast  | Fair     | Quick tests, low-quality audio OK |
| base   | ~150MB | Fast       | Good     | **Recommended** - Best balance |
| small  | ~500MB | Moderate   | Better   | Higher quality needed |
| medium | ~1.5GB | Slow       | High     | Professional transcription |
| large  | ~3GB   | Very Slow  | Best     | Maximum accuracy required |

## Performance Expectations

### Transcript API (Normal)
- **Time:** 1-3 seconds per video
- **Cost:** Free (uses YouTube's official API)

### Audio Fallback (When Activated)
- **Download:** 10-30 seconds (depends on video length)
- **Transcription (base model, CPU):** 30-60 seconds
- **Transcription (base model, GPU):** 10-25 seconds
- **Total:** 40-90 seconds per video
- **Cost:** Free (all local processing)

## GPU Acceleration

If you have an NVIDIA GPU with CUDA:

1. Install CUDA-enabled PyTorch:
```bash
# Check CUDA version: nvidia-smi
# Install matching PyTorch from: https://pytorch.org/get-started/locally/

# Example for CUDA 11.8:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

2. Update `.env`:
```bash
WHISPER_DEVICE=cuda
```

3. Expect 3-5x faster transcription (10-25 seconds vs 30-60 seconds)

## Fallback-Only Mode

When the system detects IP blocks or consecutive failures, it automatically switches to **fallback-only mode** for remaining videos in the batch. This:

- Skips `youtube-transcript-api` entirely
- Saves 20-200 seconds per video (no wasted retry attempts)
- Continues until batch completes or process restarts

You'll see this warning when it activates:
```
⚠️ Detected IP block/consecutive failures. Switching to audio fallback for remaining videos.
```

## Video Filtering

The audio fallback system automatically **skips videos that are not suitable** for processing:

### Videos That Are Skipped

1. **Live Streams**: Currently broadcasting or scheduled streams cannot be downloaded
   - Status: `is_live`, `is_upcoming`, `post_live`
   - Warning: "Video is live stream. Cannot download audio from live/upcoming streams."

2. **Very Short Videos**: Videos shorter than 30 seconds (configurable)
   - Examples: YouTube Shorts, promotional clips, teasers
   - Warning: "Video is too short (9s < 30s). Skipping audio fallback for very short videos."
   - Reason: Processing overhead (download + Whisper) is not worth it for such short content

These videos are **not added to the video index**, allowing you to retry them later when they become available or decide to process them manually.

### Configuration

Adjust the minimum duration threshold:
```bash
# Skip videos shorter than 60 seconds
MIN_VIDEO_DURATION_SECONDS=60
```

## Troubleshooting

### "Whisper model 'base' not found"

**Solution:** Download the model first (see step 3 in Prerequisites)

### "yt-dlp not installed"

**Solution:** 
```bash
pip install yt-dlp
```

### "Whisper not installed"

**Solution:**
```bash
pip install openai-whisper
```

### "ffmpeg not found"

**Solution:** Install ffmpeg (see step 2 in Prerequisites)

### Audio download fails with "HTTP Error 403"

**Possible causes:**
- Video is region-restricted
- Video requires authentication
- YouTube is blocking downloads

**Solutions:**
- Try a VPN
- Check if video is publicly accessible
- Wait and retry later

### Transcription is slow

**Solutions:**
1. Use a smaller model (`WHISPER_MODEL=tiny`)
2. Enable GPU acceleration (if available)
3. Process fewer videos per batch

### CUDA out of memory

**Solutions:**
1. Use a smaller model (medium → small → base → tiny)
2. Close other GPU-intensive applications
3. Fall back to CPU: `WHISPER_DEVICE=cpu`

## Video Index Markers

The system tracks different failure states in `video_index.txt`:

- `VIDEO_UNAVAILABLE` - Video not accessible
- `TRANSCRIPTS_DISABLED` - Transcripts turned off
- `NO_TRANSCRIPT_FOUND` - No captions available
- `VIDEO_UNPLAYABLE` - Video cannot be played
- `IP_BLOCKED` - IP address blocked by YouTube
- `AUDIO_FALLBACK_FAILED` - Both methods failed
- `TRANSCRIPTS_DISABLED_FALLBACK_SUCCEEDED` - Fallback worked after transcript API failed
- `NO_TRANSCRIPT_FOUND_FALLBACK_SUCCEEDED` - Fallback worked after no transcript found

**Note:** Live streams and upcoming scheduled videos are NOT added to the index. They will be skipped during processing and can be retried on subsequent runs once they become available.

These markers prevent re-attempting failed videos on subsequent runs.

## Disabling the Fallback

To disable audio fallback completely:

```bash
ENABLE_AUDIO_FALLBACK=false
```

Or remove the environment variable entirely (defaults to enabled).

## Example Usage

```bash
# Normal usage - fallback activates automatically when needed
yt2md --url https://www.youtube.com/watch?v=VIDEO_ID

# Process channel - fallback activates on failures
yt2md --channel CHANNEL_ID --days 7

# Check logs to see when fallback is used
# Look for: "🔄 Activating audio fallback for..."
```

## Logs

Fallback events are logged with emoji indicators:

- 🔄 Activating audio fallback
- ⬇️ Downloading audio
- 🎤 Transcribing with Whisper
- ✅ Fallback succeeded
- ⚠️ Switching to fallback-only mode
- 💡 CUDA available but not being used

Check `logs/yt2md.log` for detailed information.

## Cost Comparison

| Method | Cost | Speed | Success Rate |
|--------|------|-------|--------------|
| Transcript API | Free | Fast (1-3s) | ~90% (when not blocked) |
| Audio Fallback | Free | Slow (40-90s) | ~95% (works when API fails) |
| Combined | Free | Varies | ~99% (best of both) |

**Note:** Both methods are completely free. The only "cost" is processing time.
