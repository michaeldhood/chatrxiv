"""
Domain models for chat aggregation.

These models represent the normalized structure of chats, messages, and workspaces
independent of Cursor's internal storage format.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
import json


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
    RESPONSE = "response"      # Actual text content
    TOOL_CALL = "tool_call"    # Tool invocation (empty text)
    THINKING = "thinking"      # Reasoning trace
    EMPTY = "empty"            # Unknown empty bubble


@dataclass
class Workspace:
    """Represents a Cursor workspace."""
    id: Optional[int] = None
    workspace_hash: str = ""
    folder_uri: str = ""
    resolved_path: Optional[str] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "workspace_hash": self.workspace_hash,
            "folder_uri": self.folder_uri,
            "resolved_path": self.resolved_path,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


@dataclass
class Message:
    """Represents a single message in a chat."""
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
        """Convert to dictionary for database storage."""
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


@dataclass
class Chat:
    """Represents a complete chat conversation."""
    id: Optional[int] = None
    cursor_composer_id: str = ""
    workspace_id: Optional[int] = None
    title: str = ""
    mode: ChatMode = ChatMode.CHAT
    created_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    source: str = "cursor"  # "cursor" or "legacy"
    messages: List[Message] = None
    relevant_files: List[str] = None

    def __post_init__(self):
        """Initialize default values."""
        if self.messages is None:
            self.messages = []
        if self.relevant_files is None:
            self.relevant_files = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "cursor_composer_id": self.cursor_composer_id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "mode": self.mode.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
            "source": self.source,
        }


@dataclass
class Canvas:
    """
    Represents an infinite canvas for organizing chats visually.
    
    Canvases allow users to drag chats onto a 2D space and arrange them
    freely. Chats are linked (not copied) so they stay in sync.
    """
    id: Optional[int] = None
    name: str = "Untitled Canvas"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Viewport state: {"x": 0, "y": 0, "zoom": 1.0}
    viewport: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize default values."""
        if self.viewport is None:
            self.viewport = {"x": 0, "y": 0, "zoom": 1.0}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "viewport": json.dumps(self.viewport) if self.viewport else None,
        }


@dataclass
class CanvasChatNode:
    """
    Represents a chat placed on a canvas at a specific position.
    
    This is a LINK to the chat, not a copy. The chat_id references
    the actual chat, so any updates to the chat are reflected here.
    """
    id: Optional[int] = None
    canvas_id: int = 0
    chat_id: int = 0
    position_x: float = 0.0
    position_y: float = 0.0
    width: float = 400.0  # Default card width
    height: float = 300.0  # Default card height
    z_index: int = 0
    collapsed: bool = False  # Whether the card shows preview or full detail

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "canvas_id": self.canvas_id,
            "chat_id": self.chat_id,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "width": self.width,
            "height": self.height,
            "z_index": self.z_index,
            "collapsed": self.collapsed,
        }

