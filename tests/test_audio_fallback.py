"""Tests for audio fallback transcript extraction."""

import builtins
from unittest.mock import MagicMock, Mock, patch

import pytest

from yt2md.audio_fallback import (
    AudioDownloadError,
    NewAndLongVideoError,
    _check_new_and_long_video,
    _format_duration,
    TranscriptionError,
    WhisperModelNotFoundError,
    extract_transcript_via_audio,
    is_fallback_enabled,
)


class TestFallbackEnabled:
    """Tests for is_fallback_enabled function."""

    def test_fallback_enabled_true(self, monkeypatch):
        """Test fallback is enabled when ENABLE_AUDIO_FALLBACK=true."""
        monkeypatch.setenv("ENABLE_AUDIO_FALLBACK", "true")
        assert is_fallback_enabled() is True

    def test_fallback_enabled_1(self, monkeypatch):
        """Test fallback is enabled when ENABLE_AUDIO_FALLBACK=1."""
        monkeypatch.setenv("ENABLE_AUDIO_FALLBACK", "1")
        assert is_fallback_enabled() is True

    def test_fallback_enabled_yes(self, monkeypatch):
        """Test fallback is enabled when ENABLE_AUDIO_FALLBACK=yes."""
        monkeypatch.setenv("ENABLE_AUDIO_FALLBACK", "yes")
        assert is_fallback_enabled() is True

    def test_fallback_disabled_false(self, monkeypatch):
        """Test fallback is disabled when ENABLE_AUDIO_FALLBACK=false."""
        monkeypatch.setenv("ENABLE_AUDIO_FALLBACK", "false")
        assert is_fallback_enabled() is False

    def test_fallback_disabled_0(self, monkeypatch):
        """Test fallback is disabled when ENABLE_AUDIO_FALLBACK=0."""
        monkeypatch.setenv("ENABLE_AUDIO_FALLBACK", "0")
        assert is_fallback_enabled() is False

    def test_fallback_default_enabled(self, monkeypatch):
        """Test fallback is enabled by default when env var not set."""
        monkeypatch.delenv("ENABLE_AUDIO_FALLBACK", raising=False)
        assert is_fallback_enabled() is True


class TestExtractTranscriptViaAudio:
    """Tests for extract_transcript_via_audio function."""

    def test_successful_extraction(self, monkeypatch, tmp_path):
        """Test successful transcript extraction via audio fallback."""
        # Mock environment variables
        monkeypatch.setenv("MAX_AUDIO_SIZE_MB", "100")
        monkeypatch.setenv("AUDIO_CACHE_DIR", str(tmp_path))

        # Create a temporary audio file
        audio_file = tmp_path / "test_video.mp3"
        audio_file.write_bytes(b"fake audio data")

        # Mock _download_audio_ytdlp to return the temp file path
        mock_download = Mock(return_value=str(audio_file))
        monkeypatch.setattr("yt2md.audio_fallback._download_audio_ytdlp", mock_download)

        # Mock _transcribe_whisper_local to return test transcript
        mock_transcribe = Mock(return_value="This is a test transcript")
        monkeypatch.setattr(
            "yt2md.audio_fallback._transcribe_whisper_local", mock_transcribe
        )

        result = extract_transcript_via_audio(
            "https://www.youtube.com/watch?v=test123", "en"
        )

        assert result == "This is a test transcript"
        assert mock_download.called
        assert mock_transcribe.called
        # Audio file should be cleaned up
        assert not audio_file.exists()

    def test_audio_download_failure(self, monkeypatch, tmp_path):
        """Test handling of audio download failure."""
        monkeypatch.setenv("AUDIO_CACHE_DIR", str(tmp_path))

        # Mock _download_audio_ytdlp to return None (download failed)
        mock_download = Mock(return_value=None)
        monkeypatch.setattr("yt2md.audio_fallback._download_audio_ytdlp", mock_download)

        result = extract_transcript_via_audio(
            "https://www.youtube.com/watch?v=test123", "en"
        )

        assert result is None
        assert mock_download.called

    def test_audio_too_large(self, monkeypatch, tmp_path):
        """Test handling of audio file exceeding size limit."""
        monkeypatch.setenv("MAX_AUDIO_SIZE_MB", "1")  # 1MB limit
        monkeypatch.setenv("AUDIO_CACHE_DIR", str(tmp_path))

        # Create a large temporary audio file (2MB)
        audio_file = tmp_path / "large_video.mp3"
        audio_file.write_bytes(b"x" * (2 * 1024 * 1024))  # 2MB

        mock_download = Mock(return_value=str(audio_file))
        monkeypatch.setattr("yt2md.audio_fallback._download_audio_ytdlp", mock_download)

        result = extract_transcript_via_audio(
            "https://www.youtube.com/watch?v=test123", "en"
        )

        assert result is None
        assert mock_download.called
        # Audio file should still be cleaned up
        assert not audio_file.exists()

    def test_transcription_failure(self, monkeypatch, tmp_path):
        """Test handling of transcription failure."""
        monkeypatch.setenv("MAX_AUDIO_SIZE_MB", "100")
        monkeypatch.setenv("AUDIO_CACHE_DIR", str(tmp_path))

        audio_file = tmp_path / "test_video.mp3"
        audio_file.write_bytes(b"fake audio data")

        mock_download = Mock(return_value=str(audio_file))
        monkeypatch.setattr("yt2md.audio_fallback._download_audio_ytdlp", mock_download)

        # Mock _transcribe_whisper_local to raise TranscriptionError
        mock_transcribe = Mock(side_effect=TranscriptionError("Transcription failed"))
        monkeypatch.setattr(
            "yt2md.audio_fallback._transcribe_whisper_local", mock_transcribe
        )

        result = extract_transcript_via_audio(
            "https://www.youtube.com/watch?v=test123", "en"
        )

        assert result is None
        assert mock_download.called
        assert mock_transcribe.called
        # Audio file should be cleaned up even on failure
        assert not audio_file.exists()

    def test_whisper_model_not_found(self, monkeypatch, tmp_path):
        """Test handling when Whisper model is not available."""
        monkeypatch.setenv("MAX_AUDIO_SIZE_MB", "100")
        monkeypatch.setenv("AUDIO_CACHE_DIR", str(tmp_path))

        audio_file = tmp_path / "test_video.mp3"
        audio_file.write_bytes(b"fake audio data")

        mock_download = Mock(return_value=str(audio_file))
        monkeypatch.setattr("yt2md.audio_fallback._download_audio_ytdlp", mock_download)

        # Mock _transcribe_whisper_local to raise WhisperModelNotFoundError
        mock_transcribe = Mock(
            side_effect=WhisperModelNotFoundError("Model 'base' not found")
        )
        monkeypatch.setattr(
            "yt2md.audio_fallback._transcribe_whisper_local", mock_transcribe
        )

        result = extract_transcript_via_audio(
            "https://www.youtube.com/watch?v=test123", "en"
        )

        assert result is None
        assert mock_download.called
        assert mock_transcribe.called
        # Audio file should be cleaned up
        assert not audio_file.exists()


class TestDownloadAudioYtdlp:
    """Tests for _download_audio_ytdlp function."""

    def test_yt_dlp_not_installed(self, monkeypatch):
        """Test error handling when yt-dlp is not installed."""
        # Mock the import to raise ImportError
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "yt_dlp":
                raise ImportError("No module named 'yt_dlp'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        from yt2md.audio_fallback import _download_audio_ytdlp

        with pytest.raises(AudioDownloadError, match="yt-dlp not installed"):
            _download_audio_ytdlp("https://www.youtube.com/watch?v=test123")

    def test_download_audio_skips_new_and_long_video(self, monkeypatch):
        """Test _download_audio_ytdlp raises NewAndLongVideoError without downloading audio."""
        import time
        from yt2md.audio_fallback import _download_audio_ytdlp

        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            "id": "newlong123",
            "duration": 3500,
            "timestamp": time.time() - 3600,
            "is_live": False,
        }
        mock_ydl.__enter__.return_value = mock_ydl
        mock_ydl.__exit__.return_value = None
        mock_ydl_class = MagicMock(return_value=mock_ydl)

        with patch("yt_dlp.YoutubeDL", mock_ydl_class):
            with pytest.raises(NewAndLongVideoError):
                _download_audio_ytdlp("https://www.youtube.com/watch?v=newlong123")

        # Verify extract_info was called with download=False, but never with download=True
        assert mock_ydl.extract_info.call_count == 1
        args, kwargs = mock_ydl.extract_info.call_args
        assert kwargs.get("download") is False


class TestTranscribeWhisperLocal:
    """Tests for _transcribe_whisper_local function."""

    def test_whisper_not_installed(self, monkeypatch, tmp_path):
        """Test error handling when Whisper is not installed."""
        # Mock the import to raise ImportError
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "whisper":
                raise ImportError("No module named 'whisper'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        from yt2md.audio_fallback import _transcribe_whisper_local

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        with pytest.raises(TranscriptionError, match="Whisper not installed"):
            _transcribe_whisper_local(str(audio_file), "en")

    def test_whisper_model_not_found_error(self, monkeypatch, tmp_path):
        """Test handling when Whisper model file is not found."""
        monkeypatch.setenv("WHISPER_MODEL", "base")
        monkeypatch.setenv("WHISPER_DEVICE", "cpu")

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        # Mock whisper and torch imports
        mock_whisper = MagicMock()
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        # Mock load_model to raise FileNotFoundError
        mock_whisper.load_model.side_effect = FileNotFoundError(
            "No such file or directory: 'base.pt'"
        )

        with patch.dict("sys.modules", {"whisper": mock_whisper, "torch": mock_torch}):
            from yt2md.audio_fallback import _transcribe_whisper_local

            with pytest.raises(
                WhisperModelNotFoundError, match="Whisper model 'base' not found"
            ):
                _transcribe_whisper_local(str(audio_file), "en")

    def test_cuda_available_warning(self, monkeypatch, tmp_path, capsys):
        """Test logging when CUDA is available but not being used."""
        monkeypatch.setenv("WHISPER_MODEL", "base")
        monkeypatch.setenv("WHISPER_DEVICE", "cpu")

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        # Mock whisper and torch
        mock_whisper = MagicMock()
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True  # CUDA available

        mock_model = MagicMock()
        mock_result = {"text": "Test transcript"}
        mock_model.transcribe.return_value = mock_result
        mock_whisper.load_model.return_value = mock_model

        with patch.dict("sys.modules", {"whisper": mock_whisper, "torch": mock_torch}):
            from yt2md.audio_fallback import _transcribe_whisper_local

            result = _transcribe_whisper_local(str(audio_file), "en")

            assert result == "Test transcript"
            # Should log CUDA availability recommendation

    def test_language_code_mapping(self, monkeypatch, tmp_path):
        """Test language code is properly mapped for Whisper."""
        monkeypatch.setenv("WHISPER_MODEL", "base")
        monkeypatch.setenv("WHISPER_DEVICE", "cpu")

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        mock_whisper = MagicMock()
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        mock_model = MagicMock()
        mock_result = {"text": "Testowy transkrypt"}
        mock_model.transcribe.return_value = mock_result
        mock_whisper.load_model.return_value = mock_model

        with patch.dict("sys.modules", {"whisper": mock_whisper, "torch": mock_torch}):
            from yt2md.audio_fallback import _transcribe_whisper_local

            result = _transcribe_whisper_local(str(audio_file), "pl")

            assert result == "Testowy transkrypt"
            # Check that language was passed as "polish"
            call_args = mock_model.transcribe.call_args
            assert call_args[1]["language"] == "polish"

    def test_empty_transcript_result(self, monkeypatch, tmp_path):
        """Test handling when Whisper returns empty transcript."""
        monkeypatch.setenv("WHISPER_MODEL", "base")
        monkeypatch.setenv("WHISPER_DEVICE", "cpu")

        audio_file = tmp_path / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        mock_whisper = MagicMock()
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        mock_model = MagicMock()
        mock_result = {"text": "   "}  # Empty/whitespace only
        mock_model.transcribe.return_value = mock_result
        mock_whisper.load_model.return_value = mock_model

        with patch.dict("sys.modules", {"whisper": mock_whisper, "torch": mock_torch}):
            from yt2md.audio_fallback import _transcribe_whisper_local

            result = _transcribe_whisper_local(str(audio_file), "en")

            assert result is None


class TestCheckNewAndLongVideo:
    """Tests for _check_new_and_long_video and _format_duration functions."""

    def test_format_duration(self):
        """Test formatting duration in seconds to human-readable strings."""
        assert _format_duration(45) == "0m 45s"
        assert _format_duration(65) == "1m 05s"
        assert _format_duration(1200) == "20m 00s"
        assert _format_duration(3593) == "59m 53s"
        assert _format_duration(3665) == "1h 01m 05s"

    def test_skip_new_and_long_video_with_timestamp(self, monkeypatch):
        """Test video is skipped when it is new (< 24h) and long (>= 1200s)."""
        import time
        from datetime import datetime, timezone

        monkeypatch.delenv("AUDIO_FALLBACK_SKIP_NEW_LONG_VIDEOS", raising=False)
        monkeypatch.delenv("AUDIO_FALLBACK_LONG_VIDEO_MIN_DURATION_SECONDS", raising=False)
        monkeypatch.delenv("AUDIO_FALLBACK_NEW_VIDEO_MAX_AGE_HOURS", raising=False)

        # Video published 2 hours ago, duration 3600s (1 hour)
        two_hours_ago = time.time() - (2 * 3600)
        info = {
            "duration": 3600,
            "timestamp": two_hours_ago,
        }

        with pytest.raises(NewAndLongVideoError, match="skipping audio fallback"):
            _check_new_and_long_video(info)

    def test_skip_new_and_long_video_with_upload_date(self, monkeypatch):
        """Test video age calculation falls back to upload_date YYYYMMDD string."""
        from datetime import datetime, timezone

        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        info = {
            "duration": 1800,  # 30 minutes
            "upload_date": today_str,
        }

        with pytest.raises(NewAndLongVideoError, match="skipping audio fallback"):
            _check_new_and_long_video(info)

    def test_not_long_enough(self):
        """Test video is not skipped if it is shorter than long duration threshold."""
        import time

        two_hours_ago = time.time() - (2 * 3600)
        info = {
            "duration": 600,  # 10 minutes (< 20 min default threshold)
            "timestamp": two_hours_ago,
        }

        # Should not raise
        _check_new_and_long_video(info)

    def test_not_new_enough(self):
        """Test video is not skipped if it is older than new video max age threshold."""
        import time

        three_days_ago = time.time() - (72 * 3600)
        info = {
            "duration": 3600,
            "timestamp": three_days_ago,
        }

        # Should not raise
        _check_new_and_long_video(info)

    def test_skip_disabled_via_env(self, monkeypatch):
        """Test skipping is bypassed when AUDIO_FALLBACK_SKIP_NEW_LONG_VIDEOS is false."""
        import time

        monkeypatch.setenv("AUDIO_FALLBACK_SKIP_NEW_LONG_VIDEOS", "false")
        two_hours_ago = time.time() - (2 * 3600)
        info = {
            "duration": 3600,
            "timestamp": two_hours_ago,
        }

        # Should not raise because feature is disabled
        _check_new_and_long_video(info)

    def test_custom_thresholds(self, monkeypatch):
        """Test custom duration and age thresholds via environment variables."""
        import time

        # Set custom thresholds: min duration 600s (10 min), max age 6 hours
        monkeypatch.setenv("AUDIO_FALLBACK_LONG_VIDEO_MIN_DURATION_SECONDS", "600")
        monkeypatch.setenv("AUDIO_FALLBACK_NEW_VIDEO_MAX_AGE_HOURS", "6")

        info_matching = {
            "duration": 700,
            "timestamp": time.time() - (4 * 3600),  # 4 hours old (<= 6h)
        }
        with pytest.raises(NewAndLongVideoError):
            _check_new_and_long_video(info_matching)

        info_too_old = {
            "duration": 700,
            "timestamp": time.time() - (8 * 3600),  # 8 hours old (> 6h)
        }
        # Should not raise
        _check_new_and_long_video(info_too_old)

    def test_missing_age_metadata(self):
        """Test video is not skipped if neither timestamp nor upload_date is present."""
        info = {
            "duration": 3600,
        }
        # Should not raise because age cannot be determined
        _check_new_and_long_video(info)


class TestExtractTranscriptViaAudioNewAndLong:
    """Tests for NewAndLongVideoError handling in extract_transcript_via_audio."""

    def test_re_raises_new_and_long_video_error(self, monkeypatch):
        """Test extract_transcript_via_audio re-raises NewAndLongVideoError to caller."""
        mock_download = Mock(
            side_effect=NewAndLongVideoError("Video is new and long, skipping")
        )
        monkeypatch.setattr("yt2md.audio_fallback._download_audio_ytdlp", mock_download)

        with pytest.raises(NewAndLongVideoError, match="Video is new and long"):
            extract_transcript_via_audio("https://www.youtube.com/watch?v=new123", "en")


class TestYoutubeNewAndLongSkip:
    """Tests for get_youtube_transcript skipping new and long videos without indexing."""

    def test_get_youtube_transcript_skips_and_avoids_indexing(self, monkeypatch):
        """Test that get_youtube_transcript skips new/long video without adding to index."""
        from youtube_transcript_api._errors import NoTranscriptFound
        from yt2md.youtube import get_youtube_transcript

        # Mock YouTubeTranscriptApi to raise NoTranscriptFound
        mock_api = MagicMock()
        mock_api.fetch.side_effect = NoTranscriptFound("video_id", ["en"], [])
        monkeypatch.setattr("yt2md.youtube.YouTubeTranscriptApi", lambda: mock_api)

        # Mock _try_audio_fallback to raise NewAndLongVideoError
        mock_fallback = Mock(
            side_effect=NewAndLongVideoError("Video is new and long, skipping")
        )
        monkeypatch.setattr("yt2md.youtube._try_audio_fallback", mock_fallback)

        mock_update_index = Mock()
        monkeypatch.setattr("yt2md.youtube.update_video_index", mock_update_index)

        mock_increment_counter = Mock()
        monkeypatch.setattr("yt2md.youtube._increment_failure_counter", mock_increment_counter)

        result = get_youtube_transcript("https://www.youtube.com/watch?v=_kNc-n9Q26M", "pl")

        assert result is None
        # Must NOT add to video index!
        mock_update_index.assert_not_called()
        # Must NOT count as failure!
        mock_increment_counter.assert_not_called()

