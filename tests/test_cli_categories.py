import unittest
from unittest.mock import patch, MagicMock

from yt2md.cli import parse_args, parse_categories
from yt2md.video_collector import collect_videos_from_category


class TestCategoriesParsing(unittest.TestCase):
    def test_parse_categories_single_string(self):
        self.assertEqual(parse_categories("Fitness"), ["Fitness"])

    def test_parse_categories_comma_separated(self):
        self.assertEqual(parse_categories("Fitness, News"), ["Fitness", "News"])
        self.assertEqual(parse_categories("Fitness,News"), ["Fitness", "News"])

    def test_parse_categories_multiple_arg_list(self):
        self.assertEqual(parse_categories(["Fitness,", "News"]), ["Fitness", "News"])
        self.assertEqual(parse_categories(["Fitness", "News"]), ["Fitness", "News"])

    def test_parse_categories_nested_lists(self):
        self.assertEqual(
            parse_categories([["Fitness, News"], ["IT"]]),
            ["Fitness", "News", "IT"],
        )

    def test_parse_categories_deduplication_and_whitespace(self):
        self.assertEqual(
            parse_categories([" Fitness ", "News", "Fitness, IT "]),
            ["Fitness", "News", "IT"],
        )

    def test_parse_categories_empty_or_none(self):
        self.assertEqual(parse_categories(None), [])
        self.assertEqual(parse_categories(""), [])
        self.assertEqual(parse_categories([]), [])

    def test_cli_parse_args_category_comma_separated(self):
        args = parse_args(["--category", "Fitness, News", "--days", "1"])
        categories = parse_categories(args.category)
        self.assertEqual(categories, ["Fitness", "News"])

    def test_cli_parse_args_category_multiple_args(self):
        args = parse_args(["--category", "Fitness", "News", "--days", "1"])
        categories = parse_categories(args.category)
        self.assertEqual(categories, ["Fitness", "News"])

    def test_cli_parse_args_category_repeated_flags(self):
        args = parse_args(["--category", "Fitness", "--category", "News", "--days", "1"])
        categories = parse_categories(args.category)
        self.assertEqual(categories, ["Fitness", "News"])


class TestCollectVideosFromCategory(unittest.TestCase):
    @patch("yt2md.video_collector.load_channels_by_category")
    @patch("yt2md.video_collector._collect_videos_from_single_channel")
    def test_collect_videos_multiple_categories(self, mock_collect_single, mock_load_channels):
        channel_fitness = MagicMock(id="ch_fit", name="FitChannel", category="Fitness")
        channel_news = MagicMock(id="ch_news", name="NewsChannel", category="News")

        def load_channels_side_effect(cat):
            if cat == "Fitness":
                return [channel_fitness]
            elif cat == "News":
                return [channel_news]
            return []

        mock_load_channels.side_effect = load_channels_side_effect

        mock_collect_single.side_effect = [
            [("http://fit1", "Fit Video 1", "2026-08-06", "FitChannel", "en", "English", "Fitness")],
            [("http://news1", "News Video 1", "2026-08-06", "NewsChannel", "en", "English", "News")],
        ]

        result = collect_videos_from_category("Fitness, News", days=1)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "http://fit1")
        self.assertEqual(result[0][6], "Fitness")
        self.assertEqual(result[1][0], "http://news1")
        self.assertEqual(result[1][6], "News")

    @patch("yt2md.video_collector.logger")
    @patch("yt2md.video_collector.load_channels_by_category")
    def test_collect_videos_podcast_category_log_skipped(self, mock_load_channels, mock_logger):
        mock_load_channels.return_value = []
        collect_videos_from_category("Podcast", days=1)
        
        # Verify logger.info was not called with "Processing videos from categories:"
        for call_args in mock_logger.info.call_args_list:
            msg = call_args[0][0]
            self.assertNotIn("Processing videos from categories:", msg)


class TestMainWithCategoriesAndPodcast(unittest.TestCase):
    @patch.dict("os.environ", {"GEMINI_API_KEY": "mock_key"})
    @patch("yt2md.main.setup_logging")
    @patch("yt2md.podcast.process_podcast_subscriptions")
    @patch("yt2md.main.collect_videos_from_category")
    @patch("yt2md.main.display_video_processing_summary")
    @patch("yt2md.processor.process_videos")
    def test_run_main_with_categories_and_podcast_flag(
        self, mock_process_videos, mock_display_summary, mock_collect, mock_podcast_sub, mock_logging
    ):
        from yt2md.main import run_main
        args = parse_args(["--category", "Fitness", "--category", "News", "--days", "1", "--podcast"])
        
        mock_collect.return_value = [("http://vid1", "Vid 1", "2026-08-06", "Chan", "en", "English", "Fitness")]
        
        run_main(args)

        # Podcast RSS sync should be called
        mock_podcast_sub.assert_called_once_with(days=1, channel_name=None, max_videos=10)
        
        # Video collection should still be called for Fitness and News categories
        mock_collect.assert_called_once_with(["Fitness", "News"], 1, channel_name=None, max_videos=10)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "mock_key"})
    @patch("yt2md.main.setup_logging")
    @patch("yt2md.config.load_channels_by_category", return_value=[MagicMock()])
    @patch("yt2md.podcast.process_podcast_subscriptions")
    @patch("yt2md.main.collect_videos_from_category")
    @patch("yt2md.main.display_video_processing_summary")
    @patch("yt2md.processor.process_videos")
    def test_run_main_with_podcast_in_categories_filters_podcast_from_markdown(
        self, mock_process_videos, mock_display_summary, mock_collect, mock_podcast_sub, mock_load_cat, mock_logging
    ):
        from yt2md.main import run_main
        args = parse_args(["--category", "Fitness, News, Podcast", "--days", "1"])
        
        mock_collect.return_value = [("http://vid1", "Vid 1", "2026-08-06", "Chan", "en", "English", "Fitness")]
        
        run_main(args)

        # Podcast RSS sync should be called
        mock_podcast_sub.assert_called_once_with(days=1, channel_name=None, max_videos=10)
        
        # Video collection should filter out Podcast and only collect Fitness and News
        mock_collect.assert_called_once_with(["Fitness", "News"], 1, channel_name=None, max_videos=10)


if __name__ == "__main__":
    unittest.main()
