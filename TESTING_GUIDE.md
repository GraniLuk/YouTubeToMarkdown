# Testing the Audio Fallback Feature

## Prerequisites

Before testing, ensure you have:

1. **Installed dependencies:**
```powershell
pip install yt-dlp openai-whisper torch ffmpeg-python
```

2. **Installed FFmpeg:**
```powershell
choco install ffmpeg
```

3. **Downloaded Whisper model:**
```powershell
echo "test" > dummy.mp3
whisper --model base --language English dummy.mp3
Remove-Item dummy.mp3
```

4. **Configured .env:**
```bash
ENABLE_AUDIO_FALLBACK=true
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
```

## Test Method 1: Run Unit Tests

Test the fallback components in isolation:

```powershell
# Run all audio fallback tests
pytest tests/test_audio_fallback.py -v

# Run specific test
pytest tests/test_audio_fallback.py::TestFallbackEnabled::test_fallback_enabled_true -v

# Run with coverage
pytest tests/test_audio_fallback.py --cov=yt2md.audio_fallback
```

## Test Method 2: Manual Interactive Test

Use the provided test script:

```powershell
python test_fallback_manual.py
```

This will:
1. Check if all dependencies are installed
2. Let you choose test mode:
   - **Option 1:** Direct fallback test (bypasses transcript API)
   - **Option 2:** Full integration test (tries API first, fallback on failure)
   - **Option 3:** Both tests
3. Prompt for a YouTube URL
4. Show detailed results and logs

**Example:**
```powershell
PS> python test_fallback_manual.py

Choose test mode:
1. Test audio fallback directly (bypass transcript API)
2. Test full integration (try transcript API first, fallback if fails)
3. Both

Enter choice (1-3): 1
Enter YouTube video URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ
Enter language code (default: en): en

# Watch the logs for:
# 🔄 Activating audio fallback
# ⬇️ Downloading audio
# 🎤 Transcribing with Whisper
# ✅ Fallback succeeded
```

## Test Method 3: Real-World Video Test

Find a video with no transcripts and process it:

```powershell
# 1. Find a video where transcripts are disabled
#    (Look for creator content, music videos, or older videos)

# 2. Try processing with yt2md
yt2md --url "https://www.youtube.com/watch?v=VIDEO_ID"

# 3. Check the logs
Get-Content logs/yt2md.log | Select-String "fallback"
```

**Expected log output:**
```
WARNING - No transcripts available for video
INFO - 🔄 Activating audio fallback for https://...
INFO - ⬇️ Downloading audio: VIDEO_ID
INFO - 🎤 Transcribing with Whisper (model: base, device: cpu)...
INFO - ✅ Fallback succeeded: 1543 words extracted
```

## Test Method 4: Simulate IP Block

Force a failure to trigger fallback mode:

```powershell
# Temporarily disable transcript API by modifying youtube.py
# Or use test_fallback_manual.py option 1 to bypass API entirely
python test_fallback_manual.py
# Choose option 1
```

## Test Method 5: Test Consecutive Failures

Process multiple videos where transcripts fail:

```powershell
# Create a test file with 5 URLs that have no transcripts
# Process them and watch for fallback-only mode activation

# Expected after 3 failures:
# ⚠️ Detected IP block/consecutive failures. 
# Switching to audio fallback for remaining videos.
```

## Validation Checklist

After running tests, verify:

- [ ] Audio files are downloaded to `AUDIO_CACHE_DIR`
- [ ] Audio files are cleaned up after processing
- [ ] Transcript is extracted and returned as string
- [ ] Video index is updated correctly
- [ ] Fallback-only mode activates after threshold
- [ ] CUDA recommendation appears if GPU available
- [ ] Error messages are clear and helpful
- [ ] Processing time is reasonable (30-90 seconds)

## Quick Smoke Test

Fastest way to verify it works:

```powershell
# 1. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Run the manual test script with a short video
python test_fallback_manual.py

# 3. Choose option 1 (direct fallback)

# 4. Enter this short test video (30 seconds):
# https://www.youtube.com/watch?v=jNQXAC9IVRw
# (Or any YouTube Shorts / short video)

# 5. Wait ~40-60 seconds

# 6. Verify you get a transcript back
```

## Troubleshooting Test Issues

### "Import whisper could not be resolved"
**Solution:** Install dependencies first:
```powershell
pip install openai-whisper
```

### "Whisper model 'base' not found"
**Solution:** Download the model:
```powershell
echo "test" > dummy.mp3
whisper --model base --language English dummy.mp3
```

### Tests hang or timeout
**Solution:** 
- Use a shorter video (< 2 minutes)
- Check internet connection
- Verify FFmpeg is installed: `ffmpeg -version`

### "ffmpeg not found"
**Solution:**
```powershell
choco install ffmpeg
# Restart terminal after installation
```

## Performance Benchmarks

Expected timing for different video lengths:

| Video Length | Download | Transcribe (CPU) | Total |
|--------------|----------|------------------|-------|
| 1 min        | ~5s      | ~10s            | ~15s  |
| 5 min        | ~15s     | ~40s            | ~55s  |
| 10 min       | ~25s     | ~80s            | ~105s |
| 20 min       | ~45s     | ~160s           | ~205s |

Start with a 1-2 minute video for initial testing!

## Next Steps

Once basic tests pass:

1. Test with different languages (pl, es, fr, etc.)
2. Test with different Whisper models (tiny, small, large)
3. Test GPU acceleration if CUDA available
4. Test full batch processing with mixed success/failure
5. Test the video_index.txt markers are correct
