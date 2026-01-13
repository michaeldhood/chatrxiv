"""
Pydantic models for ChatGPT export data.

These models represent the structure of data from ChatGPT export files
(conversations.json), before normalization into domain models. Uses hybrid
validation: strict for critical fields, lenient for optional/unknown fields.

Based on export schema: docs/chatgpt/export-schema.md
"""

from enum import StrEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AuthorRole(StrEnum):
    """Author role in ChatGPT messages."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageStatus(StrEnum):
    """Message status in ChatGPT."""

    FINISHED_SUCCESSFULLY = "finished_successfully"
    # Other statuses may exist but not documented


class ChatGPTAuthor(BaseModel):
    """Author information for a ChatGPT message."""

    model_config = ConfigDict(extra="allow")

    role: AuthorRole = Field(..., description="Author role: 'user', 'assistant', or 'system'")
    name: Optional[str] = Field(None, description="Author name (usually null)")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Author metadata (may contain real_author, source, etc.)"
    )


class ChatGPTContent(BaseModel):
    """Content object for a ChatGPT message."""

    model_config = ConfigDict(extra="allow")

    content_type: str = Field(
        ..., description="Content type (usually 'text')"
    )
    parts: List[Any] = Field(
        default_factory=list, description="List of content parts (strings for text messages)"
    )


class ChatGPTMessage(BaseModel):
    """Message object within a ChatGPT node."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Message UUID (usually same as node ID)")
    author: ChatGPTAuthor = Field(..., description="Author information")
    create_time: Optional[float] = Field(
        None, description="Unix timestamp when message was created"
    )
    update_time: Optional[float] = Field(
        None, description="Unix timestamp when message was updated"
    )
    content: ChatGPTContent = Field(..., description="Content object")
    status: MessageStatus = Field(
        ..., description="Message status (e.g., 'finished_successfully')"
    )
    end_turn: Optional[bool] = Field(None, description="Whether this ends a turn")
    weight: Optional[float] = Field(
        None, description="Branch weight (higher = more recent/main path)"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional metadata (request_id, model_slug, etc.)"
    )
    recipient: Optional[str] = Field(None, description="Recipient (usually 'all')")
    channel: Optional[str] = Field(None, description="Channel information")


class ChatGPTNode(BaseModel):
    """
    Node in ChatGPT's message tree structure.

    ChatGPT uses a tree to support branching conversations where users
    can branch off from earlier messages.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Node UUID (same as the mapping key)")
    parent: Optional[str] = Field(
        None, description="Parent node ID (null for root nodes)"
    )
    children: List[str] = Field(
        default_factory=list, description="List of child node IDs"
    )
    message: Optional[ChatGPTMessage] = Field(
        None, description="Message object (null for container nodes)"
    )


class ChatGPTConversation(BaseModel):
    """
    Root conversation object from ChatGPT export.

    Represents a conversation with metadata and a message tree structure.
    """

    model_config = ConfigDict(extra="allow")

    conversation_id: str = Field(..., description="Unique UUID identifier for the conversation")
    id: str = Field(..., description="Same as conversation_id")
    title: str = Field(..., description="Conversation title")
    create_time: float = Field(
        ..., description="Unix timestamp (seconds since epoch) when conversation was created"
    )
    update_time: float = Field(
        ..., description="Unix timestamp when conversation was last updated"
    )
    current_node: str = Field(..., description="UUID of the current/latest message node")
    mapping: Dict[str, ChatGPTNode] = Field(
        ..., description="Message tree structure (key: node ID, value: node object)"
    )
    is_archived: Optional[bool] = Field(None, description="Whether conversation is archived")
    is_do_not_remember: Optional[bool] = Field(
        None, description="Whether conversation is excluded from memory"
    )
    is_study_mode: Optional[bool] = Field(None, description="Whether conversation is in study mode")
    default_model_slug: Optional[str] = Field(
        None, description="Model used (e.g., 'gpt-5-2')"
    )
    memory_scope: Optional[str] = Field(
        None, description="Memory scope setting (e.g., 'global_enabled')"
    )
    blocked_urls: Optional[List[str]] = Field(None, description="List of blocked URLs")
    safe_urls: Optional[List[str]] = Field(None, description="List of safe URLs")
    moderation_results: Optional[List[Any]] = Field(
        None, description="Moderation results (usually empty)"
    )
    disabled_tool_ids: Optional[List[str]] = Field(None, description="List of disabled tool IDs")
    conversation_template_id: Optional[str] = Field(
        None, description="Template ID if used"
    )
    gizmo_id: Optional[str] = Field(None, description="Custom GPT/Gizmo ID if used")
    gizmo_type: Optional[str] = Field(None, description="Type of gizmo")
    plugin_ids: Optional[str] = Field(None, description="Plugin IDs")
    voice: Optional[str] = Field(None, description="Voice setting")
    owner: Optional[str] = Field(None, description="Owner information")
    pinned_time: Optional[float] = Field(None, description="Timestamp when pinned")
    is_starred: Optional[bool] = Field(None, description="Whether conversation is starred")
    is_read_only: Optional[bool] = Field(None, description="Whether conversation is read-only")
    sugar_item_id: Optional[str] = Field(None, description="Internal item ID")
    sugar_item_visible: Optional[bool] = Field(None, description="Visibility flag")
    async_status: Optional[str] = Field(None, description="Async operation status")
    context_scopes: Optional[Any] = Field(None, description="Context scope settings")
    conversation_origin: Optional[str] = Field(None, description="Origin of conversation")
