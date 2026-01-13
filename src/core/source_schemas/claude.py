"""
Pydantic models for Claude.ai conversation data.

These models represent the structure of data from Claude.ai's internal API,
before normalization into domain models. Uses hybrid validation: strict for
critical fields, lenient for optional/unknown fields.

Based on API reference: docs/claude/api-reference.md
"""

from enum import StrEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SenderRole(StrEnum):
    """Message sender role in Claude conversations."""

    HUMAN = "human"
    ASSISTANT = "assistant"


class ContentType(StrEnum):
    """Content block type in Claude messages."""

    TEXT = "text"
    THINKING = "thinking"


class StopReason(StrEnum):
    """Stop reason for message completion."""

    STOP_SEQUENCE = "stop_sequence"
    END_TURN = "end_turn"
    MAX_TOKENS = "max_tokens"


class ClaudeContentBlock(BaseModel):
    """Content block within a Claude message."""

    model_config = ConfigDict(extra="allow")

    type: ContentType = Field(..., description="Content type: 'text' or 'thinking'")
    text: Optional[str] = Field(None, description="Text content (for text blocks)")
    thinking: Optional[str] = Field(None, description="Thinking content (for thinking blocks)")
    citations: Optional[List[Any]] = Field(
        None, description="Source citations array"
    )
    start_timestamp: Optional[str] = Field(
        None, description="ISO timestamp when streaming started"
    )
    stop_timestamp: Optional[str] = Field(
        None, description="ISO timestamp when streaming ended"
    )


class ClaudeMessage(BaseModel):
    """Message in a Claude conversation."""

    model_config = ConfigDict(extra="allow")

    uuid: str = Field(..., description="Unique message identifier")
    sender: SenderRole = Field(..., description="Message sender: 'human' or 'assistant'")
    index: int = Field(..., description="Message order in conversation")
    content: List[ClaudeContentBlock] = Field(
        default_factory=list, description="List of content blocks"
    )
    created_at: str = Field(..., description="ISO timestamp when message was created")
    updated_at: Optional[str] = Field(
        None, description="ISO timestamp when message was updated"
    )
    stop_reason: Optional[StopReason] = Field(
        None, description="Why model stopped generating"
    )
    parent_message_uuid: Optional[str] = Field(
        None, description="Parent message UUID for branching conversations"
    )
    attachments: Optional[List[Any]] = Field(None, description="Attached files/images")
    files: Optional[List[Any]] = Field(None, description="File attachments")
    files_v2: Optional[List[Any]] = Field(None, description="File attachments v2")
    sync_sources: Optional[List[Any]] = Field(None, description="Synced data sources")
    truncated: Optional[bool] = Field(None, description="Whether message was truncated")


class ClaudeSettings(BaseModel):
    """Per-conversation feature settings."""

    model_config = ConfigDict(extra="allow")

    enabled_web_search: Optional[bool] = Field(None, description="Web search capability")
    enabled_sourdough: Optional[bool] = Field(None, description="Unknown feature (codename)")
    enabled_foccacia: Optional[bool] = Field(None, description="Unknown feature (codename)")
    enabled_mcp_tools: Optional[Dict[str, Any]] = Field(
        None, description="MCP tool integrations"
    )
    enabled_monkeys_in_a_barrel: Optional[bool] = Field(
        None, description="Unknown feature (codename)"
    )
    enabled_saffron: Optional[bool] = Field(None, description="Unknown feature (codename)")
    enabled_turmeric: Optional[bool] = Field(None, description="Unknown feature (codename)")
    preview_feature_uses_artifacts: Optional[bool] = Field(
        None, description="Artifacts enabled"
    )
    enabled_artifacts_attachments: Optional[bool] = Field(
        None, description="Artifact attachments enabled"
    )


class ClaudeConversation(BaseModel):
    """
    Root conversation object from Claude.ai API.

    Represents a full conversation with metadata, settings, and messages.
    """

    model_config = ConfigDict(extra="allow")

    uuid: str = Field(..., description="Unique conversation identifier")
    name: Optional[str] = Field(None, description="Auto-generated or user-set title")
    summary: Optional[str] = Field(None, description="AI-generated conversation summary")
    model: str = Field(..., description="Model used (e.g., 'claude-opus-4-5-20251101')")
    created_at: str = Field(..., description="ISO timestamp when conversation was created")
    updated_at: str = Field(..., description="ISO timestamp when conversation was updated")
    settings: Optional[ClaudeSettings] = Field(
        None, description="Per-conversation feature settings"
    )
    chat_messages: List[ClaudeMessage] = Field(
        default_factory=list, description="List of messages in conversation"
    )
    is_starred: Optional[bool] = Field(None, description="User starred this conversation")
    is_temporary: Optional[bool] = Field(
        None, description="Temporary/ephemeral conversation"
    )
    platform: Optional[str] = Field(
        None, description="Source platform (usually 'CLAUDE_AI')"
    )
    current_leaf_message_uuid: Optional[str] = Field(
        None, description="Points to active branch tip in tree structure"
    )
