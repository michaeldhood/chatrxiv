"""
Domain models for chat aggregation and GitHub activity.

These models represent the normalized structure of chats, messages, workspaces,
and GitHub activity (commits, PRs) independent of source storage formats.
"""
from dataclasses import dataclass, field
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


# =============================================================================
# GitHub Activity Models
# =============================================================================

class PRState(str, Enum):
    """Pull request state."""
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class ActivityLinkType(str, Enum):
    """How a chat-activity link was established."""
    WORKSPACE_TEMPORAL = "workspace_temporal"  # Same workspace, activity within time window
    FILE_OVERLAP = "file_overlap"              # Shared files between chat and commit/PR
    BRANCH_MATCH = "branch_match"              # PR branch mentioned in chat
    CONTENT_MATCH = "content_match"            # Terms in commit/PR match chat content
    MANUAL = "manual"                          # User-assigned link


@dataclass
class Repository:
    """
    Represents a GitHub repository linked to a workspace.
    
    Maps the local workspace path to a GitHub owner/repo.
    """
    id: Optional[int] = None
    workspace_id: Optional[int] = None
    owner: str = ""                    # e.g., "anthropics"
    name: str = ""                     # e.g., "claude-code"
    full_name: str = ""                # e.g., "anthropics/claude-code"
    default_branch: str = "main"
    remote_url: str = ""               # git@github.com:... or https://...
    local_path: str = ""               # resolved local path
    last_synced_at: Optional[datetime] = None

    def __post_init__(self):
        """Compute full_name if not set."""
        if not self.full_name and self.owner and self.name:
            self.full_name = f"{self.owner}/{self.name}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "workspace_id": self.workspace_id,
            "owner": self.owner,
            "name": self.name,
            "full_name": self.full_name,
            "default_branch": self.default_branch,
            "remote_url": self.remote_url,
            "local_path": self.local_path,
            "last_synced_at": self.last_synced_at.isoformat() if self.last_synced_at else None,
        }


@dataclass
class CommitFile:
    """Represents a file changed in a commit."""
    path: str = ""
    status: str = ""        # added, modified, deleted, renamed
    additions: int = 0
    deletions: int = 0


@dataclass
class Commit:
    """
    Represents a Git commit.
    
    Stores commit metadata from GitHub for cross-referencing with chats.
    """
    id: Optional[int] = None
    repository_id: int = 0
    sha: str = ""
    short_sha: str = ""                # first 7 chars
    message: str = ""
    author_name: str = ""
    author_email: str = ""
    author_login: str = ""             # GitHub username
    authored_at: Optional[datetime] = None
    committed_at: Optional[datetime] = None
    branch: Optional[str] = None
    additions: int = 0
    deletions: int = 0
    files_changed: int = 0
    files: List[CommitFile] = field(default_factory=list)

    def __post_init__(self):
        """Compute short_sha if not set."""
        if not self.short_sha and self.sha:
            self.short_sha = self.sha[:7]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "repository_id": self.repository_id,
            "sha": self.sha,
            "short_sha": self.short_sha,
            "message": self.message,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "author_login": self.author_login,
            "authored_at": self.authored_at.isoformat() if self.authored_at else None,
            "committed_at": self.committed_at.isoformat() if self.committed_at else None,
            "branch": self.branch,
            "additions": self.additions,
            "deletions": self.deletions,
            "files_changed": self.files_changed,
        }


@dataclass
class PullRequest:
    """
    Represents a GitHub Pull Request.
    
    Stores PR metadata for cross-referencing with chats.
    """
    id: Optional[int] = None
    repository_id: int = 0
    number: int = 0
    title: str = ""
    body: str = ""
    state: PRState = PRState.OPEN
    author_login: str = ""
    base_branch: str = ""              # target branch (e.g., "main")
    head_branch: str = ""              # source branch (e.g., "feature/foo")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    merged_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    commits_count: int = 0
    commit_shas: List[str] = field(default_factory=list)  # SHAs of commits in PR

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "repository_id": self.repository_id,
            "number": self.number,
            "title": self.title,
            "body": self.body,
            "state": self.state.value,
            "author_login": self.author_login,
            "base_branch": self.base_branch,
            "head_branch": self.head_branch,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "merged_at": self.merged_at.isoformat() if self.merged_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "additions": self.additions,
            "deletions": self.deletions,
            "changed_files": self.changed_files,
            "commits_count": self.commits_count,
        }


@dataclass
class ChatActivityLink:
    """
    Links a chat to GitHub activity (commit or PR).
    
    The link includes metadata about how the link was established
    and a confidence score for relevance.
    """
    id: Optional[int] = None
    chat_id: int = 0
    activity_type: str = ""            # "commit" or "pr"
    activity_id: int = 0               # commits.id or pull_requests.id
    link_type: ActivityLinkType = ActivityLinkType.WORKSPACE_TEMPORAL
    confidence: float = 1.0            # 0.0-1.0 confidence score
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "chat_id": self.chat_id,
            "activity_type": self.activity_type,
            "activity_id": self.activity_id,
            "link_type": self.link_type.value,
            "confidence": self.confidence,
        }

