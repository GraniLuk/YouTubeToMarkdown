from typing import Any, Dict

import pytest

from yt2md import youtube


class DummyResponse:
    def __init__(self, payload: Dict[str, Any]):
        self._payload = payload

    def json(self) -> Dict[str, Any]:
        return self._payload


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


def _setup_common_mocks(monkeypatch, search_payload, videos_payload):
    def fake_get(url, params=None):
        if "youtube/v3/search" in url:
            return DummyResponse(search_payload)
        if "youtube/v3/videos" in url:
            # Ensure params dict is provided with IDs
            assert params is not None
            requested_ids = params["id"].split(",")
            items = []
            for item in videos_payload["items"]:
                if item["id"] in requested_ids:
                    items.append(item)
            return DummyResponse({"items": items})
        raise AssertionError(f"Unexpected URL requested: {url}")

    monkeypatch.setattr(youtube, "requests", type("RequestsModule", (), {"get": staticmethod(fake_get)}))
    monkeypatch.setattr(youtube, "get_processed_video_ids", lambda skip: set())
    monkeypatch.setenv("YOUTUBE_API_KEY", "dummy-key")


def test_get_videos_from_channel_skips_shorts_when_enabled(monkeypatch):
    search_payload = {
        "items": [
            {
                "id": {"videoId": "short123"},
                "snippet": {
                    "title": "Short clip",
                    "publishedAt": "2025-02-01T12:00:00Z",
                },
            },
            {
                "id": {"videoId": "video456"},
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

    _setup_common_mocks(monkeypatch, search_payload, videos_payload)

    videos = youtube.get_videos_from_channel(
        "channel-id",
        days=1,
        max_videos=5,
        skip_shorts=True,
        shorts_max_duration_seconds=75,
    )

    assert len(videos) == 1
    assert videos[0][0].endswith("video456")


def test_get_videos_from_channel_keeps_shorts_when_disabled(monkeypatch):
    search_payload = {
        "items": [
            {
                "id": {"videoId": "short123"},
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

    _setup_common_mocks(monkeypatch, search_payload, videos_payload)

    videos = youtube.get_videos_from_channel(
        "channel-id",
        days=1,
        max_videos=5,
        skip_shorts=False,
    )

    assert len(videos) == 1
    assert videos[0][0].endswith("short123")
