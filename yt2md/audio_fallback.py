"""Audio-based transcript extraction fallback using yt-dlp and Whisper."""

import os
import time
from typing import Optional

from yt2md.logger import get_logger

logger = get_logger("audio_fallback")

# Track last download time to enforce delay between downloads
_last_download_time: Optional[float] = None


class AudioDownloadError(Exception):
    """Raised when yt-dlp fails to download audio."""

    pass


class TranscriptionError(Exception):
    """Raised when Whisper fails to transcribe."""

    pass


class AudioTooLargeError(Exception):
    """Raised when audio file exceeds size limit."""

    pass


class WhisperModelNotFoundError(Exception):
    """Raised when Whisper model is not available locally."""

    pass


def extract_transcript_via_audio(
    video_url: str, language_code: str = "en"
) -> Optional[str]:
    """
    Extract transcript using audio fallback method (yt-dlp + Whisper).

    Args:
        video_url: YouTube video URL
        language_code: Language code for transcription (e.g., 'en', 'pl')

    Returns:
        Transcript text or None on failure
    """
    audio_path = None

    try:
        logger.info(f"🔄 Activating audio fallback for {video_url}")

        # Enforce delay between downloads to avoid rate limiting
        _enforce_download_delay()

        # Step 1: Download audio
        audio_path = _download_audio_ytdlp(video_url)
        if not audio_path:
            logger.error("Audio download failed")
            return None

        # Step 2: Check file size
        try:
            max_size_mb = int(os.getenv("MAX_AUDIO_SIZE_MB", "100"))
        except ValueError:
            logger.error(
                "Invalid value for environment variable MAX_AUDIO_SIZE_MB. "
                "It must be an integer."
            )
            return None
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)

        if file_size_mb > max_size_mb:
            logger.error(
                f"Audio file too large ({file_size_mb:.1f}MB > {max_size_mb}MB). Skipping."
            )
            raise AudioTooLargeError(
                f"Audio file {file_size_mb:.1f}MB exceeds limit {max_size_mb}MB"
            )

        logger.debug(f"Audio file size: {file_size_mb:.1f}MB")

        # Step 3: Transcribe with Whisper
        transcript = _transcribe_whisper_local(audio_path, language_code)

        if transcript:
            word_count = len(transcript.split())
            logger.info(f"✅ Fallback succeeded: {word_count} words extracted")
            return transcript
        else:
            logger.error("Transcription returned empty result")
            return None

    except AudioDownloadError as e:
        logger.error(f"Audio download error: {str(e)}")
        raise  # Re-raise to let caller distinguish between error types
    except TranscriptionError as e:
        logger.error(f"Transcription error: {str(e)}")
        return None
    except AudioTooLargeError as e:
        logger.error(str(e))
        return None
    except WhisperModelNotFoundError as e:
        logger.error(f"Whisper model error: {str(e)}")
        logger.error(
            "Please download the required Whisper model first. "
            "See documentation for instructions."
        )
        return None
    except Exception as e:
        logger.error(f"Unexpected error in audio fallback: {str(e)}", exc_info=True)
        return None
    finally:
        # Cleanup audio file
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                logger.debug(f"Cleaned up audio file: {audio_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup audio file {audio_path}: {str(e)}")


def _enforce_download_delay() -> None:
    """Enforce minimum delay between consecutive audio downloads to avoid rate limiting."""
    global _last_download_time

    try:
        min_delay = int(os.getenv("AUDIO_DOWNLOAD_DELAY_SECONDS", "10"))
    except ValueError:
        logger.warning("Invalid AUDIO_DOWNLOAD_DELAY_SECONDS, using default 10 seconds")
        min_delay = 10

    if _last_download_time is not None:
        time_since_last = time.time() - _last_download_time
        if time_since_last < min_delay:
            wait_time = min_delay - time_since_last
            logger.info(
                f"⏳ Waiting {wait_time:.1f}s before next download (rate limit protection)"
            )
            time.sleep(wait_time)

    _last_download_time = time.time()


def _download_audio_ytdlp(video_url: str) -> Optional[str]:
    """
    Download audio from YouTube video using yt-dlp.

    Args:
        video_url: YouTube video URL

    Returns:
        Path to downloaded audio file or None on failure
    """
    try:
        import yt_dlp  # type: ignore[import-not-found]
    except ImportError:
        logger.error("yt-dlp not installed. Install with: pip install yt-dlp")
        raise AudioDownloadError("yt-dlp not installed")

    cache_dir = os.getenv("AUDIO_CACHE_DIR", "temp_audio")
    os.makedirs(cache_dir, exist_ok=True)

    # First, check video metadata without downloading
    logger.debug("Checking video metadata (live status, duration)...")
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:  # type: ignore[arg-type]
            info = ydl.extract_info(video_url, download=False)

            # Check if video is live or upcoming
            is_live = info.get("is_live", False)
            live_status = info.get("live_status")

            if is_live or live_status in ("is_live", "is_upcoming", "post_live"):
                status_msg = "live stream" if is_live else live_status or "live"
                logger.warning(
                    f"Video is {status_msg}. Cannot download audio from live/upcoming streams."
                )
                raise AudioDownloadError(
                    f"Video is {status_msg}, not available for download"
                )

            # Check video duration (skip very short videos)
            duration = info.get("duration", 0)
            try:
                min_duration = int(os.getenv("MIN_VIDEO_DURATION_SECONDS", "30"))
            except ValueError:
                logger.warning(
                    "Invalid MIN_VIDEO_DURATION_SECONDS, using default 30 seconds"
                )
                min_duration = 30

            if duration and duration < min_duration:
                logger.warning(
                    f"Video is too short ({duration}s < {min_duration}s). "
                    f"Skipping audio fallback for very short videos."
                )
                raise AudioDownloadError(
                    f"Video too short ({duration}s), not worth processing with Whisper"
                )

            logger.debug(
                f"Video is valid (status: {live_status or 'normal'}, duration: {duration}s), proceeding..."
            )
    except AudioDownloadError:
        raise
    except Exception as e:
        logger.warning(
            f"Could not check video metadata: {str(e)}. Proceeding with download attempt..."
        )

    # Create temporary filename
    temp_template = os.path.join(cache_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": temp_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "no_color": True,
        "extract_audio": True,
    }

    # Add cookies from browser if enabled
    cookies_from_browser = os.getenv("COOKIES_FROM_BROWSER", "").lower()
    if cookies_from_browser in ("true", "1", "yes", "on", "brave"):
        # Use brave browser cookies by default, or other browser if specified
        browser_name = (
            cookies_from_browser if cookies_from_browser != "true" else "brave"
        )
        try:
            ydl_opts["cookiesfrombrowser"] = (browser_name,)
            logger.debug(f"📝 Configured to use cookies from {browser_name} browser")
        except Exception as e:
            logger.warning(
                f"Could not configure browser cookies from {browser_name}: {str(e)}"
            )

    # Get retry configuration
    try:
        max_retries_403 = int(os.getenv("AUDIO_DOWNLOAD_403_RETRIES", "1"))
    except ValueError:
        logger.warning("Invalid AUDIO_DOWNLOAD_403_RETRIES, using default 1")
        max_retries_403 = 1

    try:
        retry_delay_403 = int(
            os.getenv("AUDIO_DOWNLOAD_403_RETRY_DELAY_SECONDS", "300")
        )
    except ValueError:
        logger.warning(
            "Invalid AUDIO_DOWNLOAD_403_RETRY_DELAY_SECONDS, using default 300 seconds"
        )
        retry_delay_403 = 300

    attempt = 0
    while attempt <= max_retries_403:
        try:
            if attempt > 0:
                logger.info(
                    f"⬇️  Downloading audio (attempt {attempt + 1}/{max_retries_403 + 1}): {video_url}"
                )
            else:
                logger.info(f"⬇️  Downloading audio: {video_url}")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
                info = ydl.extract_info(video_url, download=True)
                video_id = info.get("id")

                if not video_id:
                    raise AudioDownloadError("Could not extract video ID")

                # yt-dlp should create mp3 file after post-processing
                audio_path = os.path.join(cache_dir, f"{video_id}.mp3")

                # Check if file exists and is non-empty (e.g., >1KB)
                min_audio_size = 1024  # 1KB threshold for valid audio
                if not (
                    os.path.exists(audio_path)
                    and os.path.getsize(audio_path) >= min_audio_size
                ):
                    # Try other possible extensions
                    found = False
                    for ext in ["m4a", "webm", "opus"]:
                        alt_path = os.path.join(cache_dir, f"{video_id}.{ext}")
                        if (
                            os.path.exists(alt_path)
                            and os.path.getsize(alt_path) >= min_audio_size
                        ):
                            audio_path = alt_path
                            found = True
                            break
                    if not found:
                        raise AudioDownloadError(
                            f"Downloaded audio file not found or is empty/corrupted: {audio_path}"
                        )

                logger.debug(f"Audio downloaded: {audio_path}")
                return audio_path

        except yt_dlp.DownloadError as e:  # type: ignore[attr-defined]
            error_str = str(e)
            error_str_lower = error_str.lower()
            # Check if it's a 403 error (be robust to casing and phrasing)
            is_403_error = (
                "http error 403" in error_str_lower
                or "403 forbidden" in error_str_lower
                or ("403" in error_str_lower and "forbidden" in error_str_lower)
            )
            if is_403_error:
                if attempt < max_retries_403:
                    logger.warning(
                        f"⚠️  HTTP 403 Forbidden error (YouTube rate limit). "
                        f"Waiting {retry_delay_403}s before retry {attempt + 2}/{max_retries_403 + 1}..."
                    )
                    time.sleep(retry_delay_403)
                    attempt += 1
                    continue
                else:
                    logger.error(
                        f"yt-dlp download error after {attempt + 1} attempts: {error_str}"
                    )
                    raise AudioDownloadError(
                        f"Download failed after {attempt + 1} attempts: {error_str}"
                    )
            else:
                # Non-403 error, don't retry
                logger.error(f"yt-dlp download error: {error_str}")
                raise AudioDownloadError(f"Download failed: {error_str}")
        except Exception as e:
            logger.error(f"Unexpected error during audio download: {str(e)}")
            raise AudioDownloadError(f"Download failed: {str(e)}")

    # Should never reach here, but for safety
    raise AudioDownloadError(f"Download failed after {max_retries_403 + 1} attempts")


def _transcribe_whisper_local(audio_path: str, language_code: str) -> Optional[str]:
    """
    Transcribe audio file using local Whisper model.

    Args:
        audio_path: Path to audio file
        language_code: Language code (e.g., 'en', 'pl')

    Returns:
        Transcribed text or None on failure
    """
    # Phase 1: Validate dependencies
    whisper, torch = _check_whisper_dependencies()

    # Phase 2: Load Whisper model
    model, device = _load_whisper_model(whisper, torch)

    # Phase 3: Perform transcription
    return _perform_transcription(model, audio_path, language_code, device)


def _check_whisper_dependencies():
    """Validate that Whisper and torch are installed."""
    try:
        import torch  # type: ignore[import-not-found]
        import whisper  # type: ignore[import-not-found]

        return whisper, torch
    except ImportError as e:
        logger.error(
            f"Whisper dependencies not installed: {str(e)}. "
            "Install with: pip install openai-whisper torch"
        )
        raise TranscriptionError("Whisper not installed")


def _load_whisper_model(whisper, torch):
    """Load Whisper model with proper error handling."""
    model_name = os.getenv("WHISPER_MODEL", "base")
    device = os.getenv("WHISPER_DEVICE", "cpu")

    # Check if CUDA is available but not being used
    if device == "cpu" and torch.cuda.is_available():
        logger.info(
            "💡 CUDA detected but using CPU. Set WHISPER_DEVICE=cuda for faster transcription."
        )

    logger.info(f"🎤 Loading Whisper model (model: {model_name}, device: {device})...")

    try:
        model = whisper.load_model(model_name, device=device)
        return model, device
    except Exception as e:
        error_msg = str(e).lower()
        if "no such file" in error_msg or "not found" in error_msg:
            raise WhisperModelNotFoundError(
                f"Whisper model '{model_name}' not found. "
                f"Please download it first by running: "
                f"whisper --model {model_name} --language English 'test.mp3'"
            )
        raise TranscriptionError(f"Failed to load Whisper model: {str(e)}")


def _perform_transcription(
    model, audio_path: str, language_code: str, device: str
) -> Optional[str]:
    """Execute Whisper transcription."""
    # Map common language codes to full names
    language_map = {
        "en": "english",
        "pl": "polish",
        "es": "spanish",
        "fr": "french",
        "de": "german",
        "it": "italian",
        "pt": "portuguese",
        "ru": "russian",
        "ja": "japanese",
        "ko": "korean",
        "zh": "chinese",
    }

    whisper_language = language_map.get(language_code.lower(), language_code.lower())

    logger.info(f"🎤 Transcribing audio (language: {whisper_language})...")

    try:
        result = model.transcribe(
            audio_path,
            language=whisper_language if whisper_language != "auto" else None,
            fp16=(device == "cuda"),
            verbose=False,
        )

        transcript_text = result.get("text", "").strip()

        if not transcript_text:
            logger.warning("Whisper returned empty transcript")
            return None

        logger.debug(f"Transcription completed: {len(transcript_text)} characters")
        return transcript_text

    except Exception as e:
        logger.error(f"Transcription failed: {str(e)}", exc_info=True)
        raise TranscriptionError(f"Transcription failed: {str(e)}")


def is_fallback_enabled() -> bool:
    """Check if audio fallback is enabled via environment variable."""
    enabled = os.getenv("ENABLE_AUDIO_FALLBACK", "true").lower()
    return enabled in ("true", "1", "yes", "on")
