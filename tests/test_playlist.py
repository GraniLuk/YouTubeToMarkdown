import unittest
from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET

from yt2md.channel import Channel
from yt2md.config import _create_channel
from yt2md.youtube import extract_playlist_id, is_playlist_url, get_videos_from_playlist
from yt2md.video_collector import collect_videos_from_url, _collect_videos_from_single_channel
from yt2md.podcast import process_podcast_playlist


class TestPlaylistDetection(unittest.TestCase):
    def test_channel_is_playlist_auto_detection(self):
        ch_playlist = Channel(
            id="PL1234567890abcdef",
            language_code="pl",
            output_language="Polish",
            category="Podcast",
            name="My Playlist",
        )
        self.assertTrue(ch_playlist.is_playlist)

        ch_regular = Channel(
            id="UC1234567890abcdef",
            language_code="pl",
            output_language="Polish",
            category="IT",
            name="Regular Channel",
        )
        self.assertFalse(ch_regular.is_playlist)

    def test_channel_is_playlist_explicit(self):
        ch = Channel(
            id="custom_id",
            language_code="en",
            output_language="English",
            category="News",
            name="Explicit Playlist",
            is_playlist=True,
        )
        self.assertTrue(ch.is_playlist)

    def test_create_channel_from_dict(self):
        data = {
            "id": "PLabcdef123456",
            "name": "Dict Playlist",
            "language_code": "pl",
            "output_language": "Polish",
            "is_playlist": True,
        }
        channel = _create_channel(data, "Podcast")
        self.assertTrue(channel.is_playlist)
        self.assertEqual(channel.name, "Dict Playlist")

    def test_is_playlist_url(self):
        self.assertTrue(is_playlist_url("https://www.youtube.com/playlist?list=PL12345"))
        self.assertTrue(is_playlist_url("https://youtube.com/playlist?list=PL12345"))
        self.assertTrue(is_playlist_url("PL1234567890abcdef"))
        self.assertTrue(is_playlist_url("UU1234567890abcdef"))
        self.assertTrue(is_playlist_url("https://www.youtube.com/watch?list=PL12345"))
        self.assertFalse(is_playlist_url("https://www.youtube.com/watch?v=12345678901"))
        self.assertFalse(is_playlist_url("UC1234567890abcdef"))
        self.assertFalse(is_playlist_url(""))

    def test_extract_playlist_id(self):
        self.assertEqual(
            extract_playlist_id("https://www.youtube.com/playlist?list=PLxyz123"),
            "PLxyz123",
        )
        self.assertEqual(
            extract_playlist_id("https://www.youtube.com/watch?v=abc&list=PLxyz123"),
            "PLxyz123",
        )
        self.assertEqual(extract_playlist_id("PLxyz123"), "PLxyz123")
        self.assertIsNone(extract_playlist_id("https://www.youtube.com/watch?v=abc"))


class TestPlaylistExtraction(unittest.TestCase):
    @patch("yt2md.youtube.get_processed_video_ids")
    @patch("yt_dlp.YoutubeDL")
    def test_get_videos_from_playlist(self, mock_ydl_cls, mock_get_processed):
        mock_get_processed.return_value = {"vid2"}  # vid2 is already processed

        mock_ydl_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl_instance

        mock_ydl_instance.extract_info.return_value = {
            "title": "Podcast Playlist",
            "entries": [
                {
                    "id": "vid1",
                    "title": "Episode 1",
                    "upload_date": "20260810",
                    "uploader": "Host A",
                    "url": "https://www.youtube.com/watch?v=vid1",
                },
                {
                    "id": "vid2",
                    "title": "Episode 2",
                    "upload_date": "20260811",
                    "uploader": "Host A",
                    "url": "https://www.youtube.com/watch?v=vid2",
                },
                {
                    "id": "vid3",
                    "title": "Episode 3",
                    "upload_date": "20260812",
                    "uploader": "Host A",
                    "url": "https://www.youtube.com/watch?v=vid3",
                },
            ],
        }

        videos = get_videos_from_playlist("PLtestplaylist", max_videos=10)

        # vid2 should be skipped, and order should be reversed (vid3, vid1 -> reversed: vid3 was last in list, vid1 first)
        # un-processed list before reverse: [vid1, vid3] -> reversed: [vid3, vid1]
        self.assertEqual(len(videos), 2)
        self.assertEqual(videos[0][0], "https://www.youtube.com/watch?v=vid3")
        self.assertEqual(videos[1][0], "https://www.youtube.com/watch?v=vid1")
        self.assertEqual(videos[0][1], "Episode 3")
        self.assertEqual(videos[0][2], "2026-08-12")
        self.assertEqual(videos[0][3], "Host A")

    @patch("yt2md.video_collector.get_videos_from_playlist")
    def test_collect_videos_from_url_playlist(self, mock_get_playlist):
        mock_get_playlist.return_value = [
            ("https://www.youtube.com/watch?v=vid1", "Ep 1", "2026-08-10", "Channel X"),
            ("https://www.youtube.com/watch?v=vid2", "Ep 2", "2026-08-11", "Channel X"),
        ]

        results = collect_videos_from_url(
            "https://www.youtube.com/playlist?list=PL123",
            language_code="pl",
            category="Podcast",
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0], "https://www.youtube.com/watch?v=vid1")
        self.assertEqual(results[0][1], "Ep 1")
        self.assertEqual(results[0][3], "Channel X")
        self.assertEqual(results[0][4], "pl")
        self.assertEqual(results[0][5], "Polish")
        self.assertEqual(results[0][6], "Podcast")

    @patch("yt2md.video_collector.get_videos_from_playlist")
    def test_collect_videos_from_single_channel_playlist(self, mock_get_playlist):
        mock_get_playlist.return_value = [
            ("https://www.youtube.com/watch?v=vid1", "Ep 1", "2026-08-10", "My Channel"),
        ]

        channel = Channel(
            id="PL12345",
            language_code="pl",
            output_language="Polish",
            category="Podcast",
            name="My Channel",
            is_playlist=True,
        )

        results = _collect_videos_from_single_channel(channel, days=3, max_videos=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "https://www.youtube.com/watch?v=vid1")
        self.assertEqual(results[0][1], "Ep 1")
        self.assertEqual(results[0][3], "My Channel")


class TestPodcastPlaylist(unittest.TestCase):
    @patch("yt2md.podcast.process_podcast_download")
    @patch("yt2md.podcast.get_dropbox_client")
    @patch("yt2md.podcast.fetch_or_create_rss_xml")
    @patch("yt2md.youtube.get_videos_from_playlist")
    def test_process_podcast_playlist(
        self, mock_get_videos, mock_fetch_rss, mock_get_dbx, mock_download
    ):
        mock_get_videos.return_value = [
            ("https://www.youtube.com/watch?v=vid1", "Episode 1", "2026-08-10", "Host"),
            ("https://www.youtube.com/watch?v=vid2", "Episode 2", "2026-08-11", "Host"),
        ]

        # Fake RSS XML without existing episodes
        root = ET.Element("rss", {"version": "2.0"})
        ET.SubElement(root, "channel")
        tree = ET.ElementTree(root)
        mock_fetch_rss.return_value = tree

        mock_dbx = MagicMock()
        mock_get_dbx.return_value = mock_dbx
        mock_download.return_value = tree

        process_podcast_playlist("PLtest", max_videos=5)

        self.assertEqual(mock_download.call_count, 2)
        mock_download.assert_any_call(
            "https://www.youtube.com/watch?v=vid1", dbx=mock_dbx, tree=tree
        )
        mock_download.assert_any_call(
            "https://www.youtube.com/watch?v=vid2", dbx=mock_dbx, tree=tree
        )


if __name__ == "__main__":
    unittest.main()
