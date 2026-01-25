"""
Domain models for chat aggregation.

These models represent the normalized structure of chats, messages, and workspaces
independent of Cursor's internal storage format.

All models use Pydantic for validation, serialization, and type safety.
"""

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChatMode(str, Enum):
    """Chat mode types from Cursor."""

    CHAT = "chat"
    EDIT = "edit"
    AGENT = "agent"
    COMPOSER = "composer"
    PLAN = "plan"
    DEBUG = "debug"
    ASK = "ask"


class MessageRole(str, Enum):
    """Message role types."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class MessageType(str, Enum):
    """Message content type classification."""

    RESPONSE = "response"  # Actual text content
    TOOL_CALL = "tool_call"  # Tool invocation (empty text)
    THINKING = "thinking"  # Reasoning trace
    EMPTY = "empty"  # Unknown empty bubble


class Workspace(BaseModel):
    """
    Represents a Cursor workspace.

    Domain model for workspace metadata, independent of Cursor's storage format.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: Optional[int] = None
    workspace_hash: str = ""
    folder_uri: str = ""
    resolved_path: Optional[str] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for database storage.

        Backward compatibility method. Use model_dump() for Pydantic serialization.
        """
        return {
            "workspace_hash": self.workspace_hash,
            "folder_uri": self.folder_uri,
            "resolved_path": self.resolved_path,
            "first_seen_at": self.first_seen_at.isoformat()
            if self.first_seen_at
            else None,
            "last_seen_at": self.last_seen_at.isoformat()
            if self.last_seen_at
            else None,
        }


class Message(BaseModel):
    """
    Represents a single message in a chat.

    Domain model for individual messages, independent of source format.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: Optional[int] = None
    chat_id: Optional[int] = None
    role: MessageRole = MessageRole.USER
    text: str = ""
    rich_text: str = ""
    created_at: Optional[datetime] = None
    cursor_bubble_id: Optional[str] = None
    raw_json: Optional[Dict[str, Any]] = None
    message_type: MessageType = MessageType.RESPONSE

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for database storage.

        Backward compatibility method. Use model_dump() for Pydantic serialization.
        """
        return {
            "chat_id": self.chat_id,
            "role": self.role.value,
            "text": self.text,
            "rich_text": self.rich_text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "cursor_bubble_id": self.cursor_bubble_id,
            "raw_json": json.dumps(self.raw_json) if self.raw_json else None,
            "message_type": self.message_type.value,
        }


class Chat(BaseModel):
    """
    Represents a complete chat conversation.

    Domain model for chat conversations, independent of source format (Cursor, Claude, ChatGPT).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: Optional[int] = None
    cursor_composer_id: str = ""
    workspace_id: Optional[int] = None
    title: str = ""
    mode: ChatMode = ChatMode.CHAT
    created_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    source: str = "cursor"  # "cursor", "claude.ai", "chatgpt", "claude-code", or "legacy"
    summary: Optional[str] = None  # LLM-generated summary
    model: Optional[str] = None  # AI model used (e.g., "claude-3-5-sonnet-20241022")
    estimated_cost: Optional[float] = None  # Estimated cost in USD
    messages: List[Message] = Field(default_factory=list)
    relevant_files: List[str] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for database storage.

        Backward compatibility method. Use model_dump() for Pydantic serialization.
        """
        return {
            "cursor_composer_id": self.cursor_composer_id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "mode": self.mode.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_updated_at": self.last_updated_at.isoformat()
            if self.last_updated_at
            else None,
            "source": self.source,
            "model": self.model,
            "estimated_cost": self.estimated_cost,
        }


class CursorActivity(BaseModel):
    """
    Represents a cursor activity/usage event from exported CSV data.

    Domain model for Cursor activity/usage tracking data.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: Optional[int] = None
    date: Optional[datetime] = None
    kind: str = ""  # e.g., "Included"
    model: Optional[str] = None
    max_mode: Optional[bool] = None
    input_tokens_with_cache: Optional[int] = None
    input_tokens_no_cache: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for database storage.

        Backward compatibility method. Use model_dump() for Pydantic serialization.
        """
        return {
            "date": self.date.isoformat() if self.date else None,
            "kind": self.kind,
            "model": self.model,
            "max_mode": self.max_mode,
            "input_tokens_with_cache": self.input_tokens_with_cache,
            "input_tokens_no_cache": self.input_tokens_no_cache,
            "cache_read_tokens": self.cache_read_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost": self.cost,
        }
