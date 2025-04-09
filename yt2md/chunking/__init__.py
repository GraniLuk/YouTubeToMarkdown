"""
Chunking module for splitting text into manageable pieces.
"""

from yt2md.chunking.strategies import (
    ChunkingStrategy, 
    WordChunkingStrategy,
    ChunkingStrategyFactory,
    DEFAULT_STRATEGY
)

__all__ = [
    'ChunkingStrategy',
    'WordChunkingStrategy',
    'ChunkingStrategyFactory',
    'DEFAULT_STRATEGY'
]
