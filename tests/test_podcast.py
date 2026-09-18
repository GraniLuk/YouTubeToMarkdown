import unittest
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

from yt2md.podcast import fetch_or_create_rss_xml, update_rss_feed, clean_old_episodes


class DummyDbx:
    def files_download(self, path):
        raise Exception("not found")


class TestPodcastRssFeed(unittest.TestCase):
    def test_rss_namespace_preservation_and_roundtrip(self):
        """Test that adding episodes and round-tripping through XML parsing preserves itunes namespace prefix."""
        # 1. Create initial feed & add Episode 1
        dbx = DummyDbx()
        tree = fetch_or_create_rss_xml(dbx, "/podcast.xml")
        update_rss_feed(
            tree,
            video_title="Episode 1",
            video_url="http://url1",
            audio_direct_url="http://audio1",
            file_size=100,
            duration_seconds=300,
            description="desc 1",
            video_id="id1",
        )
        xml1 = ET.tostring(tree.getroot(), encoding="utf-8").decode("utf-8")
        self.assertIn('xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"', xml1)
        self.assertIn("<itunes:duration>05:00</itunes:duration>", xml1)
        self.assertNotIn("ns0:", xml1)

        # 2. Parse xml1 back (simulating second upload / fetch from Dropbox)
        root2 = ET.fromstring(xml1)
        tree2 = ET.ElementTree(root2)
        update_rss_feed(
            tree2,
            video_title="Episode 2",
            video_url="http://url2",
            audio_direct_url="http://audio2",
            file_size=200,
            duration_seconds=600,
            description="desc 2",
            video_id="id2",
        )
        xml2 = ET.tostring(tree2.getroot(), encoding="utf-8").decode("utf-8")
        self.assertIn('xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"', xml2)
        self.assertIn("<itunes:duration>10:00</itunes:duration>", xml2)
        self.assertIn("<itunes:duration>05:00</itunes:duration>", xml2)
        self.assertNotIn("ns0:", xml2)

    def test_duplicate_episode_updates_link(self):
        """Test that updating an existing episode by guid updates the enclosure without adding a new item."""
        dbx = DummyDbx()
        tree = fetch_or_create_rss_xml(dbx, "/podcast.xml")
        update_rss_feed(
            tree,
            video_title="Episode 1",
            video_url="http://url1",
            audio_direct_url="http://audio1_old",
            file_size=100,
            duration_seconds=300,
            description="desc 1",
            video_id="id1",
        )
        update_rss_feed(
            tree,
            video_title="Episode 1",
            video_url="http://url1",
            audio_direct_url="http://audio1_new",
            file_size=150,
            duration_seconds=300,
            description="desc 1",
            video_id="id1",
        )
        items = tree.getroot().findall(".//item")
        self.assertEqual(len(items), 1)
        enclosure = items[0].find("enclosure")
        self.assertIsNotNone(enclosure)
        self.assertEqual(enclosure.get("url"), "http://audio1_new")
        self.assertEqual(enclosure.get("length"), "150")

    def test_clean_old_episodes(self):
        """Test that old excess episodes beyond max_episodes are cleaned up and deleted from Dropbox."""
        import dropbox.files
        dbx_mock = MagicMock()
        dbx_mock.files_download.side_effect = Exception("not found")

        mock_entries = []
        for i in range(1, 6):
            f_meta = MagicMock(spec=dropbox.files.FileMetadata)
            f_meta.name = f"Episode_{i}_id{i}.m4a"
            mock_entries.append(f_meta)
        dbx_mock.files_list_folder.return_value = MagicMock(entries=mock_entries)

        tree = fetch_or_create_rss_xml(dbx_mock, "/podcast.xml")
        for i in range(1, 6):
            update_rss_feed(
                tree,
                video_title=f"Episode {i}",
                video_url=f"http://url{i}",
                audio_direct_url=f"https://dl.dropboxusercontent.com/s/xyz/ep{i}.m4a?raw=1",
                file_size=100,
                duration_seconds=300,
                description=f"desc {i}",
                video_id=f"id{i}",
            )

        items_before = tree.getroot().findall(".//item")
        self.assertEqual(len(items_before), 5)

        # Clean with max_episodes = 3
        clean_old_episodes(dbx_mock, tree, max_episodes=3)

        items_after = tree.getroot().findall(".//item")
        self.assertEqual(len(items_after), 3)
        # Episodes 1 and 2 (the oldest inserted at bottom) should be removed
        guids = [item.find("guid").text for item in items_after]
        self.assertEqual(guids, ["id5", "id4", "id3"])
        self.assertEqual(dbx_mock.files_delete_v2.call_count, 2)


    def test_fetch_or_create_rss_xml_raises_on_generic_error(self):
        """Test that transient network or API errors raise an exception instead of creating an empty feed."""
        dbx_mock = MagicMock()
        dbx_mock.files_download.side_effect = RuntimeError("500 Internal Server Error")

        with self.assertRaises(RuntimeError):
            fetch_or_create_rss_xml(dbx_mock, "/podcast.xml")
        self.assertEqual(dbx_mock.files_download.call_count, 3)


class TestPodcastLiveStreamAndErrorHandling(unittest.TestCase):
    def test_is_live_or_upcoming_error(self):
        from yt2md.youtube import _is_live_or_upcoming_error
        import yt_dlp

        self.assertTrue(_is_live_or_upcoming_error(Exception("This live event will begin in 16 hours.")))
        self.assertTrue(_is_live_or_upcoming_error(Exception("ERROR: [youtube] nur_f3lEEvE: This live event will begin in 16 hours.")))
        self.assertTrue(_is_live_or_upcoming_error(yt_dlp.utils.DownloadError("This live event will begin in 2 days.")))
        self.assertTrue(_is_live_or_upcoming_error(Exception("Premieres in 3 hours")))
        self.assertTrue(_is_live_or_upcoming_error(Exception("Video is an upcoming live stream")))
        self.assertFalse(_is_live_or_upcoming_error(Exception("File not found on disk")))
        self.assertFalse(_is_live_or_upcoming_error(Exception("HTTP Error 404: Not Found")))

    def test_process_podcast_subscriptions_skips_live_stream_and_continues(self):
        from unittest.mock import patch
        from yt2md.podcast import process_podcast_subscriptions
        import yt_dlp

        videos = [
            ("https://www.youtube.com/watch?v=live123", "OKTAGON LIVE MMA", "2026-08-17", "Kanal"),
            ("https://www.youtube.com/watch?v=vid1", "Podcast Episode 1", "2026-08-17", "Kanal"),
            ("https://www.youtube.com/watch?v=vid2", "Podcast Episode 2", "2026-08-17", "Kanal"),
        ]

        dummy_tree = ET.ElementTree(ET.Element("rss", {"version": "2.0"}))
        channel_elem = ET.SubElement(dummy_tree.getroot(), "channel")

        with patch("yt2md.video_collector.collect_videos_from_category", return_value=videos), \
             patch("yt2md.podcast.get_dropbox_client") as mock_get_dbx, \
             patch("yt2md.podcast.fetch_or_create_rss_xml", return_value=dummy_tree), \
             patch("yt2md.podcast.process_podcast_download") as mock_download:

            mock_dbx = MagicMock()
            mock_get_dbx.return_value = mock_dbx

            # 1st video raises scheduled live event error; remaining 2 succeed
            def side_effect(url, dbx=None, tree=None):
                if "live123" in url:
                    raise yt_dlp.utils.DownloadError("ERROR: [youtube] live123: This live event will begin in 16 hours.")
                return tree

            mock_download.side_effect = side_effect

            # Should not raise exception and should process all 3 items (skipping 1st and processing 2nd & 3rd)
            process_podcast_subscriptions(days=3)

            self.assertEqual(mock_download.call_count, 3)

    def test_process_podcast_subscriptions_handles_unexpected_error_and_continues(self):
        from unittest.mock import patch
        from yt2md.podcast import process_podcast_subscriptions

        videos = [
            ("https://www.youtube.com/watch?v=err1", "Corrupt Episode", "2026-08-17", "Kanal"),
            ("https://www.youtube.com/watch?v=good1", "Valid Episode", "2026-08-17", "Kanal"),
        ]

        dummy_tree = ET.ElementTree(ET.Element("rss", {"version": "2.0"}))
        channel_elem = ET.SubElement(dummy_tree.getroot(), "channel")

        with patch("yt2md.video_collector.collect_videos_from_category", return_value=videos), \
             patch("yt2md.podcast.get_dropbox_client") as mock_get_dbx, \
             patch("yt2md.podcast.fetch_or_create_rss_xml", return_value=dummy_tree), \
             patch("yt2md.podcast.process_podcast_download") as mock_download:

            mock_dbx = MagicMock()
            mock_get_dbx.return_value = mock_dbx

            def side_effect(url, dbx=None, tree=None):
                if "err1" in url:
                    raise RuntimeError("Unexpected audio conversion error")
                return tree

            mock_download.side_effect = side_effect

            process_podcast_subscriptions(days=3)

            self.assertEqual(mock_download.call_count, 2)


class TestPodcastIndexDeduplication(unittest.TestCase):
    @patch("yt2md.video_index.update_video_index")
    @patch("yt2md.video_index.get_processed_video_ids")
    @patch("yt2md.video_collector.collect_videos_from_category")
    @patch("yt2md.podcast.get_dropbox_client")
    @patch("yt2md.podcast.fetch_or_create_rss_xml")
    @patch("yt2md.podcast.process_podcast_download")
    def test_subscriptions_skips_indexed_video_and_syncs_rss(
        self,
        mock_download,
        mock_fetch_rss,
        mock_get_dbx,
        mock_collect,
        mock_get_processed,
        mock_update_index,
    ):
        from yt2md.podcast import process_podcast_subscriptions

        # RSS has item with guid 'rss_old_guid'
        root = ET.Element("rss", {"version": "2.0"})
        ch = ET.SubElement(root, "channel")
        it = ET.SubElement(ch, "item")
        g = ET.SubElement(it, "guid")
        g.text = "rss_old_guid"
        tree = ET.ElementTree(root)

        mock_fetch_rss.return_value = tree
        mock_get_dbx.return_value = MagicMock()
        mock_download.return_value = tree

        # local index already contains 'indexed_vid'
        mock_get_processed.return_value = {"indexed_vid"}

        mock_collect.return_value = [
            ("https://www.youtube.com/watch?v=indexed_vid", "Indexed Video"),
            ("https://www.youtube.com/watch?v=rss_old_guid", "RSS Old Video"),
            ("https://www.youtube.com/watch?v=fresh_vid", "Fresh Video"),
        ]

        process_podcast_subscriptions(days=3)

        # 1. RSS guid not in local index should be synced into video_index
        mock_update_index.assert_any_call("rss_old_guid", "PODCAST_PROCESSED")

        # 2. Only fresh_vid should be processed by process_podcast_download
        self.assertEqual(mock_download.call_count, 1)
        mock_download.assert_called_once_with(
            "https://www.youtube.com/watch?v=fresh_vid",
            dbx=mock_get_dbx.return_value,
            tree=tree,
        )

    @patch("yt2md.video_index.update_video_index")
    @patch("yt2md.video_index.get_processed_video_ids")
    @patch("yt2md.youtube.get_videos_from_playlist")
    @patch("yt2md.podcast.get_dropbox_client")
    @patch("yt2md.podcast.fetch_or_create_rss_xml")
    @patch("yt2md.podcast.process_podcast_download")
    def test_playlist_skips_indexed_video(
        self,
        mock_download,
        mock_fetch_rss,
        mock_get_dbx,
        mock_get_videos,
        mock_get_processed,
        mock_update_index,
    ):
        from yt2md.podcast import process_podcast_playlist

        root = ET.Element("rss", {"version": "2.0"})
        ET.SubElement(root, "channel")
        tree = ET.ElementTree(root)

        mock_fetch_rss.return_value = tree
        mock_get_dbx.return_value = MagicMock()
        mock_download.return_value = tree

        # local index contains 'already_done_vid'
        mock_get_processed.return_value = {"already_done_vid"}

        mock_get_videos.return_value = [
            ("https://www.youtube.com/watch?v=already_done_vid", "Already Done", "2026-09-10", "Host"),
            ("https://www.youtube.com/watch?v=new_playlist_vid", "New Episode", "2026-09-11", "Host"),
        ]

        process_podcast_playlist("PLdummy", max_videos=5)

        # Only new_playlist_vid should be downloaded
        self.assertEqual(mock_download.call_count, 1)
        mock_download.assert_called_once_with(
            "https://www.youtube.com/watch?v=new_playlist_vid",
            dbx=mock_get_dbx.return_value,
            tree=tree,
        )


if __name__ == "__main__":
    unittest.main()

