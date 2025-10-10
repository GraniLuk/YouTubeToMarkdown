from typing import Any, Dict

import pytest

from yt2md import youtube


class DummyResponse:
    def __init__(self, payload: Dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if not (200 <= self.status_code < 300):
            raise RuntimeError(f"HTTP error {self.status_code}")


@pytest.mark.parametrize(
    "duration,expected",
    [
        ("PT45S", 45),
        ("PT1M5S", 65),
        ("PT1H1M1S", 3661),
        ("PT0S", 0),
        ("INVALID", None),
        (None, None),
    ],
)
def test_parse_iso8601_duration(duration, expected):
    assert youtube._parse_iso8601_duration(duration) == expected


def _setup_common_mocks(
    monkeypatch,
    playlist_payload: Dict[str, Any],
    videos_payload: Dict[str, Any],
    channels_payload: Dict[str, Any] | None = None,
):
    channels_payload = channels_payload or {
        "items": [
            {
                "contentDetails": {
                    "relatedPlaylists": {
                        "uploads": "UPLOADS_PLAYLIST_ID",
                    }
                }
            }
        ]
    }

    def fake_get(url, params=None, timeout=None):
        if "youtube/v3/channels" in url:
            return DummyResponse(channels_payload)
        if "youtube/v3/playlistItems" in url:
            assert params is not None
            return DummyResponse(playlist_payload)
        if "youtube/v3/videos" in url:
            assert params is not None
            requested_ids = params["id"].split(",")
            items = [
                item
                for item in videos_payload.get("items", [])
                if item["id"] in requested_ids
            ]
            return DummyResponse({"items": items})
        raise AssertionError(f"Unexpected URL requested: {url}")

    monkeypatch.setattr(youtube.requests, "get", fake_get)
    monkeypatch.setattr(youtube, "get_processed_video_ids", lambda skip: set())
    monkeypatch.setattr(youtube, "_uploads_playlist_cache", {}, raising=False)
    monkeypatch.setattr(youtube, "_uploads_cache_loaded", True, raising=False)
    monkeypatch.setattr(youtube, "_uploads_cache_dirty", False, raising=False)
    monkeypatch.setattr(youtube, "_load_uploads_playlist_cache", lambda: None)
    monkeypatch.setattr(youtube, "_save_uploads_playlist_cache", lambda: None)
    monkeypatch.setenv("YOUTUBE_API_KEY", "dummy-key")


def test_get_videos_from_channel_skips_shorts_when_enabled(monkeypatch):
    playlist_payload = {
        "items": [
            {
                "contentDetails": {
                    "videoId": "short123",
                    "videoPublishedAt": "2025-02-01T12:00:00Z",
                },
                "snippet": {
                    "title": "Short clip",
                    "publishedAt": "2025-02-01T12:00:00Z",
                },
            },
            {
                "contentDetails": {
                    "videoId": "video456",
                    "videoPublishedAt": "2025-02-02T15:30:00Z",
                },
                "snippet": {
                    "title": "Long form video",
                    "publishedAt": "2025-02-02T15:30:00Z",
                },
            },
        ]
    }
    videos_payload = {
        "items": [
            {"id": "short123", "contentDetails": {"duration": "PT30S"}},
            {"id": "video456", "contentDetails": {"duration": "PT5M10S"}},
        ]
    }

    _setup_common_mocks(monkeypatch, playlist_payload, videos_payload)

    videos = youtube.get_videos_from_channel(
        "channel-id",
        days=400,
        max_videos=5,
        skip_shorts=True,
        shorts_max_duration_seconds=75,
    )

    assert len(videos) == 1
    assert videos[0][0].endswith("video456")


def test_get_videos_from_channel_keeps_shorts_when_disabled(monkeypatch):
    playlist_payload = {
        "items": [
            {
                "contentDetails": {
                    "videoId": "short123",
                    "videoPublishedAt": "2025-02-01T12:00:00Z",
                },
                "snippet": {
                    "title": "Short clip",
                    "publishedAt": "2025-02-01T12:00:00Z",
                },
            }
        ]
    }
    videos_payload = {
        "items": [
            {"id": "short123", "contentDetails": {"duration": "PT30S"}},
        ]
    }

    _setup_common_mocks(monkeypatch, playlist_payload, videos_payload)

    videos = youtube.get_videos_from_channel(
        "channel-id",
        days=400,
        max_videos=5,
        skip_shorts=False,
    )

    assert len(videos) == 1
    assert videos[0][0].endswith("short123")
