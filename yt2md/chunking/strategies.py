"""
Strategies for chunking text content.

This module implements different approaches to dividing long text into manageable chunks.
"""

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
        if strategy_type.lower() == "word":
            chunk_size = kwargs.get("chunk_size", 25000)
            return WordChunkingStrategy(chunk_size=chunk_size)
        else:
            raise ValueError(f"Unknown chunking strategy: {strategy_type}")
