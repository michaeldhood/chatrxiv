"""
Source schema models for ingestion.

These Pydantic models represent the raw data structures from various sources
(Cursor, Claude.ai, ChatGPT) before normalization into domain models.
"""

from .chatgpt import (
    AuthorRole,
    ChatGPTAuthor,
    ChatGPTConversation,
    ChatGPTContent,
    ChatGPTMessage,
    ChatGPTNode,
    MessageStatus,
)
from .claude import (
    ClaudeConversation,
    ClaudeContentBlock,
    ClaudeMessage,
    ClaudeSettings,
    ContentType,
    SenderRole,
    StopReason,
)
from .cursor import (
    Bubble,
    BubbleHeader,
    BubbleType,
    ComposerData,
    ComposerHead,
    ComposerMode,
    ComposerStatus,
    UnifiedMode,
)

__all__ = [
    # Cursor models
    "Bubble",
    "BubbleHeader",
    "BubbleType",
    "ComposerData",
    "ComposerHead",
    "ComposerMode",
    "ComposerStatus",
    "UnifiedMode",
    # Claude models
    "ClaudeConversation",
    "ClaudeContentBlock",
    "ClaudeMessage",
    "ClaudeSettings",
    "ContentType",
    "SenderRole",
    "StopReason",
    # ChatGPT models
    "AuthorRole",
    "ChatGPTAuthor",
    "ChatGPTConversation",
    "ChatGPTContent",
    "ChatGPTMessage",
    "ChatGPTNode",
    "MessageStatus",
]
