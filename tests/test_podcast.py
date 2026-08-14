import unittest
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

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


if __name__ == "__main__":
    unittest.main()

