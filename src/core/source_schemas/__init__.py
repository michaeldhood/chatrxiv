"""
Source schema models for ingestion.

These Pydantic models represent the raw data structures from various sources
(Cursor, Claude.ai, ChatGPT) before normalization into domain models.
"""

from .cursor import Bubble, BubbleHeader, ComposerData, ComposerHead

__all__ = [
    "Bubble",
    "BubbleHeader",
    "ComposerData",
    "ComposerHead",
]
