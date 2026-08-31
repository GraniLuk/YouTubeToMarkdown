import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from yt2md.channel import Channel
from yt2md.config import _create_channel, load_channels_by_category
from yt2md.instagram import (
    _clean_title_from_post,
    _parse_entry_date,
    clean_instagram_username,
    extract_instagram_id,
    get_instagram_profile_url,
    get_instagram_transcript,
    get_reel_details_from_url,
    get_reels_from_profile,
    is_instagram_url,
)
from yt2md.video_collector import (
    _collect_videos_from_single_channel,
    collect_videos_from_url,
)
from yt2md.youtube import extract_video_id


class TestInstagramModule(unittest.TestCase):
    def test_is_instagram_url(self):
        self.assertTrue(is_instagram_url("https://www.instagram.com/reel/DF2HwPvo1U5/"))
        self.assertTrue(is_instagram_url("https://instagram.com/p/DG3l_nOIu-T/"))
        self.assertTrue(is_instagram_url("https://instagr.am/reel/DF2HwPvo1U5/"))
        self.assertTrue(is_instagram_url("https://www.instagram.com/bartekkruk_/"))
        self.assertFalse(is_instagram_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertFalse(is_instagram_url("https://youtu.be/dQw4w9WgXcQ"))
        self.assertFalse(is_instagram_url(""))
        self.assertFalse(is_instagram_url(None))

    def test_extract_instagram_id(self):
        self.assertEqual(
            extract_instagram_id("https://www.instagram.com/reel/DF2HwPvo1U5/"),
            "DF2HwPvo1U5",
        )
        self.assertEqual(
            extract_instagram_id("https://www.instagram.com/p/DG3l_nOIu-T/"),
            "DG3l_nOIu-T",
        )
        self.assertEqual(
            extract_instagram_id("https://www.instagram.com/tv/Cxxxxxx/"),
            "Cxxxxxx",
        )
        self.assertEqual(
            extract_instagram_id("https://www.instagram.com/bartekkruk_/reel/DF2HwPvo1U5/"),
            "DF2HwPvo1U5",
        )
        self.assertEqual(extract_instagram_id("DF2HwPvo1U5"), "DF2HwPvo1U5")
        self.assertIsNone(extract_instagram_id("https://youtube.com/watch?v=12345"))

    def test_clean_instagram_username(self):
        self.assertEqual(clean_instagram_username("@bartekkruk_"), "bartekkruk_")
        self.assertEqual(clean_instagram_username("bartekkruk_"), "bartekkruk_")
        self.assertEqual(
            clean_instagram_username("https://www.instagram.com/bartekkruk_/"),
            "bartekkruk_",
        )
        self.assertEqual(
            clean_instagram_username("https://www.instagram.com/bartekkruk_/reels/"),
            "bartekkruk_",
        )

    def test_get_instagram_profile_url(self):
        self.assertEqual(
            get_instagram_profile_url("bartekkruk_"),
            "https://www.instagram.com/bartekkruk_/",
        )
        self.assertEqual(
            get_instagram_profile_url("@bartekkruk_"),
            "https://www.instagram.com/bartekkruk_/",
        )

    def test_clean_title_from_post(self):
        # Specific title
        entry1 = {"title": "Jak trenować siłowo z głową", "description": "Opis"}
        self.assertEqual(_clean_title_from_post(entry1, "default"), "Jak trenować siłowo z głową")

        # Generic title with description
        entry2 = {
            "title": "Instagram post #DF2HwPvo1U5",
            "description": "5 ćwiczeń na zdrowe plecy\nOto lista ćwiczeń...",
            "id": "DF2HwPvo1U5",
        }
        self.assertEqual(
            _clean_title_from_post(entry2, "default"),
            "5 ćwiczeń na zdrowe plecy",
        )

        # Fallback when description empty
        entry3 = {"title": "Instagram post #DF2HwPvo1U5", "description": "", "id": "DF2HwPvo1U5"}
        self.assertEqual(_clean_title_from_post(entry3, "default"), "default")

    def test_parse_entry_date(self):
        now_ts = 1739097891
        entry_ts = {"timestamp": now_ts}
        dt = _parse_entry_date(entry_ts)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2025)

        entry_upload = {"upload_date": "20250209"}
        dt2 = _parse_entry_date(entry_upload)
        self.assertIsNotNone(dt2)
        self.assertEqual(dt2.strftime("%Y-%m-%d"), "2025-02-09")

        self.assertIsNone(_parse_entry_date({}))

    @patch("yt2md.instagram._get_reels_from_profile_web_api", return_value=None)
    @patch("yt2md.instagram.get_processed_video_ids")
    @patch("yt_dlp.YoutubeDL")
    def test_get_reels_from_profile(self, mock_ydl_cls, mock_get_processed, mock_web_api):
        mock_get_processed.return_value = {"ALREADY_PROCESSED"}
        mock_ydl_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl_instance

        now = datetime.now(timezone.utc)
        recent_ts = (now - timedelta(days=1)).timestamp()
        old_ts = (now - timedelta(days=10)).timestamp()

        mock_ydl_instance.extract_info.return_value = {
            "entries": [
                {
                    "id": "REEL_NEW_1",
                    "title": "Instagram post #REEL_NEW_1",
                    "description": "Rolka o treningu\nWiecej tekstu...",
                    "timestamp": recent_ts,
                    "uploader": "bartekkruk_",
                },
                {
                    "id": "ALREADY_PROCESSED",
                    "title": "Processed Reel",
                    "timestamp": recent_ts,
                },
                {
                    "id": "REEL_OLD",
                    "title": "Old Reel",
                    "timestamp": old_ts,
                },
            ]
        }

        reels = get_reels_from_profile(
            "bartekkruk_",
            days=3,
            max_videos=10,
            channel_name="Bartek Kruk",
        )

        self.assertEqual(len(reels), 1)
        url, title, pub_date, uploader = reels[0]
        self.assertEqual(url, "https://www.instagram.com/reel/REEL_NEW_1/")
        self.assertEqual(title, "Rolka o treningu")
        self.assertEqual(uploader, "Bartek Kruk")

    @patch("requests.Session")
    @patch("yt2md.instagram.get_processed_video_ids")
    def test_get_reels_from_profile_web_api(self, mock_get_processed, mock_session_cls):
        from yt2md.instagram import _get_reels_from_profile_web_api
        mock_get_processed.return_value = set()
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # Mock search response (resolving PK)
        mock_search_resp = MagicMock()
        mock_search_resp.status_code = 200
        mock_search_resp.json.return_value = {
            "users": [{"user": {"username": "bartekkruk_", "pk": "12345", "full_name": "Bartek Kruk"}}]
        }

        # Mock feed response
        now = datetime.now(timezone.utc)
        recent_ts = int((now - timedelta(days=1)).timestamp())
        mock_feed_resp = MagicMock()
        mock_feed_resp.status_code = 200
        mock_feed_resp.json.return_value = {
            "items": [
                {
                    "code": "XYZ123",
                    "media_type": 2,
                    "taken_at": recent_ts,
                    "caption": {"text": "Tytuł rolki z API\nKolejna linia opisu..."},
                }
            ]
        }

        mock_session.get.side_effect = [mock_search_resp, mock_feed_resp]

        with patch("yt2md.instagram._extract_cookies_dict_from_file", return_value={"sessionid": "test"}):
            reels = _get_reels_from_profile_web_api(
                "bartekkruk_",
                days=3,
                max_videos=5,
                channel_name="Bartek Kruk",
                cookie_file="dummy_cookies.txt",
            )

        self.assertEqual(len(reels), 1)
        self.assertEqual(reels[0][0], "https://www.instagram.com/reel/XYZ123/")
        self.assertEqual(reels[0][1], "Tytuł rolki z API")
        self.assertEqual(reels[0][3], "Bartek Kruk")

    @patch("yt2md.instagram._get_reels_from_profile_web_api", return_value=[])
    @patch("yt_dlp.YoutubeDL")
    def test_get_reels_from_profile_empty_web_api_does_not_call_ytdlp(self, mock_ydl_cls, mock_web_api):
        reels = get_reels_from_profile("bartekkruk_", days=3)
        self.assertEqual(reels, [])
        mock_ydl_cls.assert_not_called()

    @patch("yt2md.instagram.get_processed_video_ids")
    @patch("yt_dlp.YoutubeDL")
    def test_get_reel_details_from_url(self, mock_ydl_cls, mock_get_processed):
        mock_get_processed.return_value = set()
        mock_ydl_instance = MagicMock()
        mock_ydl_cls.return_value.__enter__.return_value = mock_ydl_instance

        mock_ydl_instance.extract_info.return_value = {
            "id": "DF2HwPvo1U5",
            "title": "Instagram post #DF2HwPvo1U5",
            "description": "Świetny post treningowy",
            "timestamp": 1739097891,
            "uploader": "bartekkruk_",
        }

        res = get_reel_details_from_url("https://www.instagram.com/reel/DF2HwPvo1U5/")
        self.assertIsNotNone(res)
        url, title, pub_date, uploader = res
        self.assertEqual(url, "https://www.instagram.com/reel/DF2HwPvo1U5/")
        self.assertEqual(title, "Świetny post treningowy")
        self.assertEqual(uploader, "bartekkruk_")

    @patch("yt2md.instagram.get_instagram_post_caption")
    @patch("yt2md.instagram.extract_transcript_via_audio")
    def test_get_instagram_transcript(self, mock_audio, mock_caption):
        mock_audio.return_value = "Oto transkrypcja mowy z rolki."
        mock_caption.return_value = "Opis z Instagrama #trening"

        result = get_instagram_transcript("https://www.instagram.com/reel/DF2HwPvo1U5/", "pl")
        self.assertIn("Oto transkrypcja mowy z rolki.", result)
        self.assertIn("Opis z Instagrama #trening", result)


class TestChannelAndCollectorIntegration(unittest.TestCase):
    def test_channel_platform(self):
        ch = Channel(
            id="bartekkruk_",
            language_code="pl",
            output_language="Polish",
            category="Fitness",
            name="Bartek Kruk",
            platform="instagram",
        )
        self.assertTrue(ch.is_instagram)
        self.assertEqual(ch.platform, "instagram")

    def test_channel_default_platform(self):
        ch = Channel(
            id="UC1234567890",
            language_code="en",
            output_language="English",
            category="IT",
            name="Tech Channel",
        )
        self.assertFalse(ch.is_instagram)
        self.assertEqual(ch.platform, "youtube")

    def test_config_create_channel(self):
        data = {
            "id": "bartekkruk_",
            "name": "Bartek Kruk",
            "language_code": "pl",
            "output_language": "Polish",
            "platform": "instagram",
        }
        ch = _create_channel(data, "Fitness")
        self.assertTrue(ch.is_instagram)
        self.assertEqual(ch.name, "Bartek Kruk")

    def test_extract_video_id_universal(self):
        # YouTube
        self.assertEqual(
            extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            "dQw4w9WgXcQ",
        )
        # Instagram
        self.assertEqual(
            extract_video_id("https://www.instagram.com/reel/DF2HwPvo1U5/"),
            "DF2HwPvo1U5",
        )
        self.assertEqual(
            extract_video_id("https://www.instagram.com/p/DG3l_nOIu-T/"),
            "DG3l_nOIu-T",
        )

    @patch("yt2md.video_collector.get_reel_details_from_url")
    def test_collect_videos_from_url_instagram(self, mock_details):
        mock_details.return_value = (
            "https://www.instagram.com/reel/DF2HwPvo1U5/",
            "Tytuł rolki",
            "2025-02-09",
            "Bartek Kruk",
        )

        vids = collect_videos_from_url(
            "https://www.instagram.com/reel/DF2HwPvo1U5/",
            language_code="pl",
            category="Fitness",
        )

        self.assertEqual(len(vids), 1)
        url, title, pub_date, uploader, lang, out_lang, cat = vids[0]
        self.assertEqual(url, "https://www.instagram.com/reel/DF2HwPvo1U5/")
        self.assertEqual(title, "Tytuł rolki")
        self.assertEqual(uploader, "Bartek Kruk")
        self.assertEqual(lang, "pl")
        self.assertEqual(out_lang, "Polish")
        self.assertEqual(cat, "Fitness")

    @patch("yt2md.video_collector.get_reels_from_profile")
    def test_collect_videos_from_single_channel_instagram(self, mock_get_reels):
        mock_get_reels.return_value = [
            (
                "https://www.instagram.com/reel/DF2HwPvo1U5/",
                "Rolka 1",
                "2025-02-09",
                "Bartek Kruk",
            )
        ]

        ch = Channel(
            id="bartekkruk_",
            name="Bartek Kruk",
            language_code="pl",
            output_language="Polish",
            category="Fitness",
            platform="instagram",
        )

        vids = _collect_videos_from_single_channel(ch, days=3, max_videos=5)
        self.assertEqual(len(vids), 1)
        url, title, pub_date, uploader, lang, out_lang, cat = vids[0]
        self.assertEqual(url, "https://www.instagram.com/reel/DF2HwPvo1U5/")
        self.assertEqual(title, "Rolka 1")
        self.assertEqual(uploader, "Bartek Kruk")

    @patch("yt2md.video_collector.get_reels_from_profile")
    def test_collect_videos_from_all_channels_filtered(self, mock_get_reels):
        from yt2md.video_collector import collect_videos_from_all_channels

        mock_get_reels.return_value = [
            (
                "https://www.instagram.com/reel/DF2HwPvo1U5/",
                "Rolka 1",
                "2025-02-09",
                "Bartek Kruk",
            )
        ]

        vids = collect_videos_from_all_channels(days=7, channel_name="Bartek Kruk")
        self.assertEqual(len(vids), 1)
        self.assertEqual(vids[0][3], "Bartek Kruk")


if __name__ == "__main__":
    unittest.main()
