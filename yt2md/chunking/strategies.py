"""
Strategies for chunking text content.

This module implements different approaches to dividing long text into manageable chunks.
"""

import re
from abc import ABC, abstractmethod
from typing import List


class ChunkingStrategy(ABC):
    """Abstract base class for text chunking strategies."""

    @abstractmethod
    def chunk_text(self, text: str) -> List[str]:
        """
        Split the text into manageable chunks.

        Args:
            text: The input text to split into chunks

        Returns:
            List[str]: A list of text chunks
        """
        pass


class WordChunkingStrategy(ChunkingStrategy):
    """Strategy for chunking text by word count."""

    def __init__(self, chunk_size: int = 25000):
        """
        Initialize the word chunking strategy.

        Args:
            chunk_size: Maximum number of words per chunk
        """
        self.chunk_size = chunk_size

    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into chunks based on word count.

        Args:
            text: The input text to split

        Returns:
            List[str]: List of text chunks
        """
        words = text.split()
        chunks = [
            " ".join(words[i : i + self.chunk_size])
            for i in range(0, len(words), self.chunk_size)
        ]
        return chunks


def estimate_token_count(text: str) -> int:
    """Conservative token estimate for local context budgeting."""
    normalized = " ".join(text.split())
    if not normalized:
        return 0

    words = normalized.split()
    char_estimate = (len(normalized) + 3) // 4
    word_estimate = (len(words) * 13 + 9) // 10
    return max(1, char_estimate, word_estimate)


def clip_text_to_token_budget(
    text: str, max_tokens: int, *, from_end: bool = True
) -> str:
    """Clip text to an estimated token budget, preserving whole words."""
    normalized = " ".join(text.split())
    if max_tokens <= 0 or not normalized:
        return ""
    if estimate_token_count(normalized) <= max_tokens:
        return normalized

    words = normalized.split()
    low = 0
    high = len(words)
    best_count = 0

    while low <= high:
        mid = (low + high) // 2
        selected = words[-mid:] if from_end and mid else words[:mid]
        candidate = " ".join(selected)
        if estimate_token_count(candidate) <= max_tokens:
            best_count = mid
            low = mid + 1
        else:
            high = mid - 1

    if best_count == 0:
        return words[-1] if from_end else words[0]
    selected = words[-best_count:] if from_end else words[:best_count]
    return " ".join(selected)


class TokenBudgetChunkingStrategy(ChunkingStrategy):
    """Sentence-aware chunking by estimated token budget."""

    _BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")

    def __init__(self, max_tokens: int = 4000):
        """
        Initialize the token budget chunking strategy.

        Args:
            max_tokens: Maximum estimated tokens per chunk
        """
        if max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")
        self.max_tokens = max_tokens

    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into chunks based on estimated token count.

        Args:
            text: The input text to split

        Returns:
            List[str]: List of text chunks
        """
        units = self._split_units(text)
        chunks: List[str] = []
        current_units: List[str] = []

        for unit in units:
            unit_tokens = estimate_token_count(unit)
            if unit_tokens > self.max_tokens:
                if current_units:
                    chunks.append(" ".join(current_units))
                    current_units = []
                chunks.extend(self._split_oversized_unit(unit))
                continue

            candidate_units = [*current_units, unit]
            candidate = " ".join(candidate_units)
            if current_units and estimate_token_count(candidate) > self.max_tokens:
                chunks.append(" ".join(current_units))
                current_units = [unit]
            else:
                current_units = candidate_units

        if current_units:
            chunks.append(" ".join(current_units))

        return chunks

    def _split_units(self, text: str) -> List[str]:
        normalized = text.strip()
        if not normalized:
            return []
        parts = self._BOUNDARY_RE.split(normalized)
        return [" ".join(part.split()) for part in parts if part.strip()]

    def _split_oversized_unit(self, unit: str) -> List[str]:
        words = unit.split()
        chunks: List[str] = []
        current_words: List[str] = []

        for word in words:
            candidate_words = [*current_words, word]
            candidate = " ".join(candidate_words)
            if current_words and estimate_token_count(candidate) > self.max_tokens:
                chunks.append(" ".join(current_words))
                current_words = [word]
            else:
                current_words = candidate_words

        if current_words:
            chunks.append(" ".join(current_words))

        return chunks


# Default strategy name
DEFAULT_STRATEGY = "word"


class ChunkingStrategyFactory:
    """Factory class to create chunking strategies."""

    @staticmethod
    def get_strategy(
        strategy_type: str = DEFAULT_STRATEGY, **kwargs
    ) -> ChunkingStrategy:
        """
        Get the appropriate chunking strategy based on type.

        Args:
            strategy_type: Type of chunking strategy (e.g., "word")
            **kwargs: Additional parameters for the strategy, such as chunk_size

        Returns:
            ChunkingStrategy: The corresponding strategy implementation
        """
        strategy_name = strategy_type.lower()
        if strategy_name == "word":
            chunk_size = kwargs.get("chunk_size", 250)
            return WordChunkingStrategy(chunk_size=chunk_size)
        elif strategy_name in ("token", "token_budget"):
            max_tokens = kwargs.get("max_tokens", kwargs.get("chunk_size", 4000))
            return TokenBudgetChunkingStrategy(max_tokens=max_tokens)
        else:
            raise ValueError(f"Unknown chunking strategy: {strategy_type}")
