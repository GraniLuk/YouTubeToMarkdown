# Quick Start: Audio Fallback Installation

## Step 1: Install Python Dependencies

```powershell
pip install -r requirements.txt
```

This installs all required packages including:
- yt-dlp (YouTube downloader)
- openai-whisper (local speech-to-text)
- torch (Whisper dependency)
- ffmpeg-python (audio conversion)

## Step 2: Install FFmpeg

### On Windows (using Chocolatey):
```powershell
choco install ffmpeg
```

### Or download manually:
1. Go to https://ffmpeg.org/download.html
2. Download Windows build
3. Extract and add to PATH

## Step 3: Download Whisper Model

Create a dummy audio file and download the model:

```powershell
# Create dummy file
"test" | Out-File -Encoding ascii dummy.mp3

# Download base model (recommended)
whisper --model base --language English dummy.mp3

# Clean up
Remove-Item dummy.mp3
```

## Step 4: Configure Environment

Copy `.env.example` to `.env` and verify these settings:

```bash
ENABLE_AUDIO_FALLBACK=true
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
```

## Step 5: Test It

Try processing a video:

```powershell
yt2md --url https://www.youtube.com/watch?v=VIDEO_ID
```

The fallback will activate automatically if the transcript API fails.

## Verification

Check logs for these messages:
- ✅ "🔄 Activating audio fallback" - Fallback started
- ✅ "✅ Fallback succeeded: X words extracted" - Fallback worked

## Troubleshooting

If you see errors, check `AUDIO_FALLBACK.md` for detailed troubleshooting steps.
