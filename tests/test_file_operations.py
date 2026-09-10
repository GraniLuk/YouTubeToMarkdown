import os
import tempfile
import unittest
from unittest.mock import patch

from yt2md.file_operations import (
    _is_same_video_file,
    sanitize_filename,
    save_to_markdown,
)


class TestFileOperations(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_patcher = patch.dict(
            os.environ, {"SUMMARIES_PATH": self.temp_dir.name}
        )
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        self.temp_dir.cleanup()

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("Normal Title"), "Normal Title")
        self.assertEqual(
            sanitize_filename("Title: With / Invalid? Characters*"),
            "Title_ With _ Invalid_ Characters_",
        )
        self.assertEqual(sanitize_filename(""), "untitled_content")

    def test_is_same_video_file(self):
        file_path = os.path.join(self.temp_dir.name, "test_video.md")
        content = (
            "---\n"
            "title: Test Video\n"
            "source: https://www.instagram.com/reel/Dc_FCh0sb2c/\n"
            "author: '[[Fit Recenzje]]'\n"
            "---\n\n"
            "# Content\n"
        )
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Same URL
        self.assertTrue(
            _is_same_video_file(file_path, "https://www.instagram.com/reel/Dc_FCh0sb2c/")
        )
        # Different URL with same video ID
        self.assertTrue(
            _is_same_video_file(file_path, "https://instagram.com/p/Dc_FCh0sb2c/")
        )
        # Different video ID
        self.assertFalse(
            _is_same_video_file(file_path, "https://www.instagram.com/reel/Dc5imZvMfCc/")
        )
        # Non-existent file
        self.assertFalse(
            _is_same_video_file(
                os.path.join(self.temp_dir.name, "nonexistent.md"),
                "https://www.instagram.com/reel/Dc_FCh0sb2c/",
            )
        )

    def test_save_to_markdown_same_video_overwrites(self):
        url = "https://www.instagram.com/reel/Dc_FCh0sb2c/"
        path1 = save_to_markdown(
            title="Video by fit_recenzje",
            video_url=url,
            content="First version of summary",
            author="Fit Recenzje",
            published_date="2026-08-28",
            description="Opis",
            category="Fitness",
            suffix="gemma4",
        )

        with open(path1, "r", encoding="utf-8") as f:
            self.assertIn("First version of summary", f.read())

        # Re-saving same video updates/overwrites path1
        path2 = save_to_markdown(
            title="Video by fit_recenzje",
            video_url=url,
            content="Updated version of summary",
            author="Fit Recenzje",
            published_date="2026-08-28",
            description="Opis",
            category="Fitness",
            suffix="gemma4",
        )

        self.assertEqual(path1, path2)
        with open(path2, "r", encoding="utf-8") as f:
            self.assertIn("Updated version of summary", f.read())

    def test_save_to_markdown_collision_disambiguates_different_video(self):
        url1 = "https://www.instagram.com/reel/Dc_FCh0sb2c/"
        url2 = "https://www.instagram.com/reel/Dc5imZvMfCc/"

        # Both videos share the identical title "Video by fit_recenzje"
        path1 = save_to_markdown(
            title="Video by fit_recenzje",
            video_url=url1,
            content="Summary of Video 1",
            author="Fit Recenzje",
            published_date="2026-08-28",
            description="Opis 1",
            category="Fitness",
            suffix="gemma4",
        )

        path2 = save_to_markdown(
            title="Video by fit_recenzje",
            video_url=url2,
            content="Summary of Video 2",
            author="Fit Recenzje",
            published_date="2026-08-29",
            description="Opis 2",
            category="Fitness",
            suffix="gemma4",
        )

        # Path 2 must not overwrite Path 1
        self.assertNotEqual(path1, path2)
        self.assertTrue(os.path.exists(path1))
        self.assertTrue(os.path.exists(path2))

        # Check content integrity: Video 1 content preserved
        with open(path1, "r", encoding="utf-8") as f1:
            content1 = f1.read()
            self.assertIn("Summary of Video 1", content1)
            self.assertIn(url1, content1)

        # Check Video 2 content written to disambiguated path
        with open(path2, "r", encoding="utf-8") as f2:
            content2 = f2.read()
            self.assertIn("Summary of Video 2", content2)
            self.assertIn(url2, content2)

        # Path 2 should incorporate the unique video ID
        self.assertIn("Dc5imZvMfCc", os.path.basename(path2))


if __name__ == "__main__":
    unittest.main()
