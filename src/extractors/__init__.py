"""
Extractors for pulling raw data from various sources.

Part of the ELT (Extract-Load-Transform) architecture.
"""

from .base import BaseExtractor
from .chatgpt import ChatGPTExtractor
from .claude import ClaudeExtractor
from .claude_code import ClaudeCodeExtractor
from .cursor import CursorExtractor

__all__ = [
    "BaseExtractor",
    "ChatGPTExtractor",
    "ClaudeExtractor",
    "ClaudeCodeExtractor",
    "CursorExtractor",
]
