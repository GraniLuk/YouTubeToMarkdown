"""Manual test script for audio fallback feature."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from yt2md.audio_fallback import extract_transcript_via_audio, is_fallback_enabled


def test_fallback_on_video(video_url: str, language_code: str = "en"):
    """Test audio fallback on a specific video."""
    print(f"Testing audio fallback for: {video_url}")
    print(f"Language: {language_code}")
    print(f"Fallback enabled: {is_fallback_enabled()}")
    print("-" * 60)

    # Check environment configuration
    print("\nConfiguration:")
    print(f"  ENABLE_AUDIO_FALLBACK: {os.getenv('ENABLE_AUDIO_FALLBACK', 'true')}")
    print(f"  WHISPER_MODEL: {os.getenv('WHISPER_MODEL', 'base')}")
    print(f"  WHISPER_DEVICE: {os.getenv('WHISPER_DEVICE', 'cpu')}")
    print(f"  AUDIO_CACHE_DIR: {os.getenv('AUDIO_CACHE_DIR', 'temp_audio')}")
    print(f"  MAX_AUDIO_SIZE_MB: {os.getenv('MAX_AUDIO_SIZE_MB', '100')}")
    print("-" * 60)

    # Try extraction
    print("\nStarting extraction...\n")

    try:
        transcript = extract_transcript_via_audio(video_url, language_code)

        if transcript:
            print("\n" + "=" * 60)
            print("✅ SUCCESS!")
            print("=" * 60)
            print(f"\nTranscript length: {len(transcript)} characters")
            print(f"Word count: {len(transcript.split())} words")
            print("\nFirst 500 characters:")
            print("-" * 60)
            print(transcript[:500])
            if len(transcript) > 500:
                print("...")
            print("-" * 60)
            return True
        else:
            print("\n" + "=" * 60)
            print("❌ FAILED - No transcript returned")
            print("=" * 60)
            return False

    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ ERROR")
        print("=" * 60)
        print(f"Exception: {type(e).__name__}")
        print(f"Message: {str(e)}")
        import traceback

        print("\nFull traceback:")
        traceback.print_exc()
        return False


def test_fallback_integration():
    """Test the full integration with youtube.py."""
    print("\n" + "=" * 60)
    print("Testing Full Integration")
    print("=" * 60)

    from yt2md import youtube

    # Show current state
    print(f"\nFallback-only mode: {youtube._fallback_only_mode}")
    print(f"Consecutive failures: {youtube._consecutive_failures}")
    print(f"Failure threshold: {youtube._CONSECUTIVE_FAILURES_THRESHOLD}")

    # Test with a video
    test_url = input("\nEnter YouTube video URL to test: ").strip()
    if not test_url:
        print("No URL provided. Skipping integration test.")
        return

    language = input("Enter language code (default: en): ").strip() or "en"

    print("\nAttempting to get transcript using get_youtube_transcript()...")
    transcript = youtube.get_youtube_transcript(test_url, language)

    if transcript:
        print(f"\n✅ Got transcript! Length: {len(transcript)} characters")
        print(f"First 300 characters:\n{transcript[:300]}...")
    else:
        print("\n❌ Failed to get transcript")

    # Show final state
    print("\nFinal state:")
    print(f"  Fallback-only mode: {youtube._fallback_only_mode}")
    print(f"  Consecutive failures: {youtube._consecutive_failures}")


if __name__ == "__main__":
    print("=" * 60)
    print("Audio Fallback Manual Test")
    print("=" * 60)

    # Check if dependencies are installed
    try:
        import yt_dlp

        print("✅ yt-dlp is installed")
    except ImportError:
        print("❌ yt-dlp NOT installed - run: pip install yt-dlp")
        sys.exit(1)

    try:
        import whisper

        print("✅ whisper is installed")
    except ImportError:
        print("❌ whisper NOT installed - run: pip install openai-whisper")
        sys.exit(1)

    try:
        import torch

        print("✅ torch is installed")
        if torch.cuda.is_available():
            print(f"  💡 CUDA available: {torch.cuda.get_device_name(0)}")
    except ImportError:
        print("❌ torch NOT installed - run: pip install torch")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Choose test mode:")
    print("=" * 60)
    print("1. Test audio fallback directly (bypass transcript API)")
    print("2. Test full integration (try transcript API first, fallback if fails)")
    print("3. Both")

    choice = input("\nEnter choice (1-3): ").strip()

    if choice in ["1", "3"]:
        print("\n" + "=" * 60)
        print("Direct Audio Fallback Test")
        print("=" * 60)

        # Example short video for testing (you can change this)
        print("\nSuggested test URLs:")
        print("  - Any short video (< 5 min recommended for first test)")
        print("  - A video where you know transcripts are disabled")

        test_url = input("\nEnter YouTube video URL: ").strip()
        if test_url:
            language = input("Enter language code (default: en): ").strip() or "en"
            test_fallback_on_video(test_url, language)

    if choice in ["2", "3"]:
        test_fallback_integration()

    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)
