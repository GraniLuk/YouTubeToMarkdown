"""
Tests for transcript chunking strategies.
"""

import unittest

from yt2md.chunking import (
    TokenBudgetChunkingStrategy,
    clip_text_to_token_budget,
    estimate_token_count,
)


class TestTokenBudgetChunkingStrategy(unittest.TestCase):
    """Test cases for estimated-token chunking."""

    def test_sentence_chunks_stay_within_budget(self):
        text = " ".join(
            f"Sentence {i} has several words about training recovery."
            for i in range(20)
        )
        strategy = TokenBudgetChunkingStrategy(max_tokens=35)

        chunks = strategy.chunk_text(text)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(estimate_token_count(chunk), 35)

    def test_long_unpunctuated_text_is_split(self):
        text = " ".join(f"word{i}" for i in range(120))
        strategy = TokenBudgetChunkingStrategy(max_tokens=30)

        chunks = strategy.chunk_text(text)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(estimate_token_count(chunk), 30)

    def test_clip_text_to_token_budget_prefers_tail(self):
        text = " ".join(f"word{i}" for i in range(40))

        clipped = clip_text_to_token_budget(text, 10, from_end=True)

        self.assertLessEqual(estimate_token_count(clipped), 10)
        self.assertIn("word39", clipped)
        self.assertNotIn("word0", clipped)


if __name__ == "__main__":
    unittest.main()
