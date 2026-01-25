"""
Pydantic models for Claude Code (CLI) conversation data.

These models represent the structure of data from Claude Code's local JSONL files,
stored at ~/.claude/projects/{encoded-project-path}/{session-uuid}.jsonl.

Uses hybrid validation: strict for critical fields, lenient for optional/unknown fields.
"""

from enum import StrEnum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class EntryType(StrEnum):
    """Entry type in Claude Code JSONL files."""

    SUMMARY = "summary"
    FILE_HISTORY_SNAPSHOT = "file-history-snapshot"
    USER = "user"
    ASSISTANT = "assistant"


class ContentBlockType(StrEnum):
    """Content block type in Claude Code messages."""

    TEXT = "text"
    THINKING = "thinking"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


class MessageRole(StrEnum):
    """Message role in Claude Code conversations."""

    USER = "user"
    ASSISTANT = "assistant"


# --- Content Blocks ---


class TextBlock(BaseModel):
    """Text content block."""

    model_config = ConfigDict(extra="allow")

    type: Literal["text"] = Field(..., description="Block type: 'text'")
    text: str = Field(..., description="Text content")


class ThinkingBlock(BaseModel):
    """Extended thinking content block."""

    model_config = ConfigDict(extra="allow")

    type: Literal["thinking"] = Field(..., description="Block type: 'thinking'")
    thinking: str = Field(..., description="Thinking content")
    signature: Optional[str] = Field(None, description="Signature for thinking block")


class ToolUseBlock(BaseModel):
    """Tool invocation content block."""

    model_config = ConfigDict(extra="allow")

    type: Literal["tool_use"] = Field(..., description="Block type: 'tool_use'")
    id: str = Field(..., description="Tool use ID")
    name: str = Field(..., description="Tool name (e.g., 'Read', 'Bash', 'Edit')")
    input: Dict[str, Any] = Field(default_factory=dict, description="Tool input parameters")


class ToolResultContentBlock(BaseModel):
    """Content block within a tool result."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(..., description="Content type (usually 'text')")
    text: Optional[str] = Field(None, description="Text content")


class ToolResultBlock(BaseModel):
    """Tool result content block (appears in user messages)."""

    model_config = ConfigDict(extra="allow")

    type: Literal["tool_result"] = Field(..., description="Block type: 'tool_result'")
    tool_use_id: str = Field(..., description="ID of the tool_use this result corresponds to")
    content: Union[str, List[ToolResultContentBlock]] = Field(
        ..., description="Tool result content (string or array of content blocks)"
    )
    is_error: Optional[bool] = Field(None, description="Whether the tool execution failed")


# Union of all content block types
ContentBlock = Union[TextBlock, ThinkingBlock, ToolUseBlock, ToolResultBlock]


# --- Message Models ---


class UsageInfo(BaseModel):
    """Token usage information."""

    model_config = ConfigDict(extra="allow")

    input_tokens: Optional[int] = Field(None, description="Input tokens used")
    output_tokens: Optional[int] = Field(None, description="Output tokens used")
    cache_creation_input_tokens: Optional[int] = Field(
        None, description="Tokens used for cache creation"
    )
    cache_read_input_tokens: Optional[int] = Field(
        None, description="Tokens read from cache"
    )


class AssistantMessagePayload(BaseModel):
    """Payload of an assistant message."""

    model_config = ConfigDict(extra="allow")

    model: Optional[str] = Field(None, description="Model used (e.g., 'claude-opus-4-5-20251101')")
    id: Optional[str] = Field(None, description="Message ID from API")
    type: Optional[str] = Field(None, description="Message type (usually 'message')")
    role: Literal["assistant"] = Field(..., description="Role: 'assistant'")
    content: List[ContentBlock] = Field(
        default_factory=list, description="List of content blocks"
    )
    stop_reason: Optional[str] = Field(None, description="Why generation stopped")
    usage: Optional[UsageInfo] = Field(None, description="Token usage stats")


class UserMessagePayload(BaseModel):
    """Payload of a user message."""

    model_config = ConfigDict(extra="allow")

    role: Literal["user"] = Field(..., description="Role: 'user'")
    content: Union[str, List[ContentBlock]] = Field(
        ..., description="User input (string) or tool results (array of content blocks)"
    )


# --- Entry Models ---


class ThinkingMetadata(BaseModel):
    """Thinking configuration metadata."""

    model_config = ConfigDict(extra="allow")

    level: Optional[str] = Field(None, description="Thinking level: 'high', 'medium', 'low'")
    disabled: Optional[bool] = Field(None, description="Whether thinking is disabled")
    triggers: Optional[List[str]] = Field(None, description="Thinking triggers")


class BaseEntry(BaseModel):
    """Base fields for all entry types."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(..., description="Entry type")


class SummaryEntry(BaseModel):
    """Conversation summary entry (first line in JSONL)."""

    model_config = ConfigDict(extra="allow")

    type: Literal["summary"] = Field(..., description="Entry type: 'summary'")
    summary: str = Field(..., description="Conversation summary text")
    leafUuid: str = Field(..., description="UUID of the last message in active branch")


class FileHistorySnapshotEntry(BaseModel):
    """File history snapshot entry for version tracking."""

    model_config = ConfigDict(extra="allow")

    type: Literal["file-history-snapshot"] = Field(
        ..., description="Entry type: 'file-history-snapshot'"
    )
    messageId: str = Field(..., description="Associated message UUID")
    snapshot: Dict[str, Any] = Field(..., description="Snapshot data")
    isSnapshotUpdate: Optional[bool] = Field(None, description="Whether this is an update")


class UserEntry(BaseModel):
    """User message entry."""

    model_config = ConfigDict(extra="allow")

    type: Literal["user"] = Field(..., description="Entry type: 'user'")
    uuid: str = Field(..., description="Unique message identifier")
    parentUuid: Optional[str] = Field(None, description="Parent message UUID for threading")
    sessionId: str = Field(..., description="Session UUID")
    message: UserMessagePayload = Field(..., description="Message payload")
    timestamp: str = Field(..., description="ISO timestamp")
    cwd: Optional[str] = Field(None, description="Current working directory")
    gitBranch: Optional[str] = Field(None, description="Git branch name")
    version: Optional[str] = Field(None, description="Claude Code version")
    slug: Optional[str] = Field(None, description="Session slug (human-readable name)")
    isSidechain: Optional[bool] = Field(None, description="Whether this is a sidechain branch")
    userType: Optional[str] = Field(None, description="User type: 'external', 'internal'")
    thinkingMetadata: Optional[ThinkingMetadata] = Field(
        None, description="Thinking configuration"
    )
    todos: Optional[List[Any]] = Field(None, description="Todo list state")


class AssistantEntry(BaseModel):
    """Assistant message entry."""

    model_config = ConfigDict(extra="allow")

    type: Literal["assistant"] = Field(..., description="Entry type: 'assistant'")
    uuid: str = Field(..., description="Unique message identifier")
    parentUuid: Optional[str] = Field(None, description="Parent message UUID for threading")
    sessionId: str = Field(..., description="Session UUID")
    message: AssistantMessagePayload = Field(..., description="Message payload")
    timestamp: str = Field(..., description="ISO timestamp")
    requestId: Optional[str] = Field(None, description="API request ID")
    cwd: Optional[str] = Field(None, description="Current working directory")
    gitBranch: Optional[str] = Field(None, description="Git branch name")
    version: Optional[str] = Field(None, description="Claude Code version")
    slug: Optional[str] = Field(None, description="Session slug")
    isSidechain: Optional[bool] = Field(None, description="Whether this is a sidechain branch")
    userType: Optional[str] = Field(None, description="User type")


# Union of all entry types for parsing
ClaudeCodeEntry = Union[SummaryEntry, FileHistorySnapshotEntry, UserEntry, AssistantEntry]


# --- Session Metadata ---


class SessionInfo(BaseModel):
    """Session metadata from sessions.json."""

    model_config = ConfigDict(extra="allow")

    timestamp: Optional[int] = Field(None, description="Unix timestamp when session started")
    directory: Optional[str] = Field(None, description="Working directory")
    project: Optional[str] = Field(None, description="Project name")
    branch: Optional[str] = Field(None, description="Git branch")
    descriptions: Optional[List[str]] = Field(None, description="Session descriptions")
    response_count: Optional[int] = Field(None, description="Number of responses in session")


class SessionsIndex(BaseModel):
    """Root structure of sessions.json."""

    model_config = ConfigDict(extra="allow")

    sessions: Dict[str, SessionInfo] = Field(
        default_factory=dict, description="Map of session ID to session info"
    )
