"""Tests for audio fallback transcript extraction."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from yt2md.audio_fallback import (
    AudioDownloadError,
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
        original_import = __builtins__.__import__

        def mock_import(name, *args, **kwargs):
            if name == "yt_dlp":
                raise ImportError("No module named 'yt_dlp'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(__builtins__, "__import__", mock_import)

        from yt2md.audio_fallback import _download_audio_ytdlp

        with pytest.raises(AudioDownloadError, match="yt-dlp not installed"):
            _download_audio_ytdlp("https://www.youtube.com/watch?v=test123")


class TestTranscribeWhisperLocal:
    """Tests for _transcribe_whisper_local function."""

    def test_whisper_not_installed(self, monkeypatch, tmp_path):
        """Test error handling when Whisper is not installed."""
        # Mock the import to raise ImportError
        original_import = __builtins__.__import__

        def mock_import(name, *args, **kwargs):
            if name == "whisper":
                raise ImportError("No module named 'whisper'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(__builtins__, "__import__", mock_import)

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
