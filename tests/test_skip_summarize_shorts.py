import os
import pytest
from unittest.mock import patch, MagicMock

from yt2md.cli import parse_args
from yt2md.processor import process_video


def test_cli_parse_skip_summarize_shorts():
    args = parse_args(["--skip-summarize-shorts"])
    assert args.skip_summarize_shorts is True


def test_cli_parse_skip_summarize_shorts_default():
    args = parse_args([])
    assert args.skip_summarize_shorts is False


@patch("yt2md.processor.get_youtube_transcript")
@patch("yt2md.processor.save_to_markdown")
@patch("yt2md.processor.analyze_transcript_by_length")
def test_process_video_skip_summarize_shorts(mock_analyze, mock_save, mock_get_transcript, tmp_path):
    # Short transcript (5 words)
    mock_get_transcript.return_value = "This is a short video."
    mock_save.return_value = str(tmp_path / "Test_Video_Watch.md")

    results = process_video(
        video_url="https://www.youtube.com/watch?v=short123",
        video_title="Test Short Video",
        published_date="2026-08-01",
        author_name="Test Author",
        language_code="en",
        output_language="English",
        category="IT",
        skip_summarize_shorts=True,
    )

    # analyze_transcript_by_length should NOT be called
    mock_analyze.assert_not_called()
    # save_to_markdown should be called with suffix="Watch"
    mock_save.assert_called_once()
    assert mock_save.call_args[1].get("suffix") == "Watch"
    assert results == [{"path": str(tmp_path / "Test_Video_Watch.md"), "word_count": 5}]


@patch("yt2md.processor.get_youtube_transcript")
@patch("yt2md.processor.save_to_markdown")
@patch("yt2md.processor.analyze_transcript_by_length")
def test_process_video_do_not_skip_normal_videos(mock_analyze, mock_save, mock_get_transcript, tmp_path):
    # Long transcript (> short threshold of 1600 words)
    long_transcript = "word " * 2000
    mock_get_transcript.return_value = long_transcript
    mock_analyze.return_value = {"cloud": {"text": "Summary", "description": "Desc", "model_name": "gemini"}}
    mock_save.return_value = str(tmp_path / "Test_Video_gemini.md")

    results = process_video(
        video_url="https://www.youtube.com/watch?v=long123",
        video_title="Test Long Video",
        published_date="2026-08-01",
        author_name="Test Author",
        language_code="en",
        output_language="English",
        category="IT",
        skip_summarize_shorts=True,
    )

    # analyze_transcript_by_length SHOULD be called because transcript is long
    mock_analyze.assert_called_once()
