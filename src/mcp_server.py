"""
MCP server for chatrxiv chat archive access.

Exposes chat data through Model Context Protocol tools, allowing LLMs
to search, browse, and read archived conversations from Cursor, Claude,
ChatGPT, and other sources.

Transport: stdio (default) or SSE via FastMCP.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from src.core.db import Database
from src.core.config import get_default_db_path

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "chatrxiv",
    instructions=(
        "You have access to a chat archive containing conversations from AI coding "
        "assistants (Cursor, Claude, ChatGPT, etc). Use these tools to search, browse, "
        "and read archived chats. Start with list_chats or search_chats to discover "
        "conversations, then use get_chat to read full conversation threads."
    ),
)

_db: Optional[Database] = None


def _get_db() -> Database:
    """Lazy-initialize the database connection."""
    global _db
    if _db is None:
        db_path = get_default_db_path()
        _db = Database(str(db_path))
        logger.info("Opened database: %s", db_path)
    return _db


def _format_datetime(iso_str: Optional[str]) -> str:
    """Format an ISO datetime string to a human-readable form."""
    if not iso_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(iso_str)


def _chat_summary_line(chat: Dict[str, Any]) -> str:
    """Format a single chat as a compact summary line."""
    title = chat.get("title") or "(untitled)"
    chat_id = chat.get("id", "?")
    mode = chat.get("mode", "")
    source = chat.get("source", "")
    msg_count = chat.get("messages_count", 0)
    created = _format_datetime(chat.get("created_at"))
    tags = chat.get("tags", [])
    workspace = chat.get("workspace_path") or chat.get("workspace_hash") or ""

    parts = [f"[{chat_id}] {title}"]
    if mode:
        parts.append(f"mode={mode}")
    if source:
        parts.append(f"source={source}")
    parts.append(f"messages={msg_count}")
    parts.append(f"created={created}")
    if workspace:
        parts.append(f"workspace={workspace}")
    if tags:
        parts.append(f"tags={','.join(tags)}")

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_chats(
    workspace_id: Optional[int] = None,
    project_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    hide_empty: bool = True,
) -> str:
    """List chats in the archive, newest first.

    Use this to browse what conversations exist. Returns compact summaries.
    Follow up with get_chat to read a specific conversation.

    Args:
        workspace_id: Filter to a specific workspace (optional).
        project_id: Filter to a specific project (optional).
        limit: Max results to return (default 50, max 200).
        offset: Pagination offset.
        hide_empty: If True (default), exclude chats with 0 messages.
    """
    db = _get_db()
    limit = min(limit, 200)
    empty_filter = "non_empty" if hide_empty else None

    chats = db.list_chats(
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
        empty_filter=empty_filter,
        project_id=project_id,
    )
    total = db.count_chats(
        workspace_id=workspace_id,
        empty_filter=empty_filter,
        project_id=project_id,
    )

    if not chats:
        return "No chats found matching the given filters."

    lines = [f"Showing {len(chats)} of {total} chats (offset={offset}):\n"]
    for chat in chats:
        lines.append(_chat_summary_line(chat))

    if total > offset + limit:
        lines.append(f"\n... {total - offset - limit} more chats. Use offset={offset + limit} to see next page.")

    return "\n".join(lines)


@mcp.tool()
def get_chat(
    chat_id: int,
    include_thinking: bool = False,
    max_messages: Optional[int] = None,
) -> str:
    """Get a full chat conversation by its ID.

    Returns the complete message thread. Use list_chats or search_chats
    to find chat IDs first.

    Args:
        chat_id: The numeric chat ID.
        include_thinking: Include AI thinking/reasoning traces (verbose). Default False.
        max_messages: Limit the number of messages returned. None = all.
    """
    db = _get_db()
    chat = db.get_chat(chat_id)

    if not chat:
        return f"Chat with ID {chat_id} not found."

    header_parts = [
        f"# {chat.get('title') or '(untitled)'}",
        f"**ID:** {chat['id']}",
        f"**Mode:** {chat.get('mode', 'unknown')}",
        f"**Source:** {chat.get('source', 'unknown')}",
        f"**Created:** {_format_datetime(chat.get('created_at'))}",
        f"**Last updated:** {_format_datetime(chat.get('last_updated_at'))}",
        f"**Messages:** {chat.get('messages_count', 0)}",
    ]

    if chat.get("model"):
        header_parts.append(f"**Model:** {chat['model']}")
    if chat.get("summary"):
        header_parts.append(f"**Summary:** {chat['summary']}")
    if chat.get("workspace_path"):
        header_parts.append(f"**Workspace:** {chat['workspace_path']}")
    if chat.get("tags"):
        header_parts.append(f"**Tags:** {', '.join(chat['tags'])}")
    if chat.get("files"):
        header_parts.append(f"**Files:** {', '.join(chat['files'][:20])}")
        if len(chat["files"]) > 20:
            header_parts.append(f"  ... and {len(chat['files']) - 20} more files")

    header = "\n".join(header_parts)

    messages = chat.get("messages", [])
    if not include_thinking:
        messages = [m for m in messages if m.get("message_type") != "thinking"]
    if max_messages:
        messages = messages[:max_messages]

    msg_lines = []
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        text = msg.get("text", "").strip()
        if not text:
            continue
        timestamp = _format_datetime(msg.get("created_at"))
        msg_lines.append(f"\n## {role} ({timestamp})\n\n{text}")

    if not msg_lines:
        return f"{header}\n\n(No message content available)"

    return f"{header}\n{''.join(msg_lines)}"


@mcp.tool()
def search_chats(
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> str:
    """Full-text search across all chat messages.

    Searches message content using SQLite FTS5. Returns matching chats
    with relevance-ranked results. Use get_chat to read a specific result.

    Args:
        query: Search query (supports FTS5 syntax: AND, OR, NOT, "phrases", prefix*).
        limit: Max results (default 20, max 100).
        offset: Pagination offset.
    """
    db = _get_db()
    limit = min(limit, 100)

    try:
        results = db.search_chats(query, limit=limit, offset=offset)
        total = db.count_search(query)
    except Exception as e:
        return f"Search error: {e}\n\nTip: Use simple keywords. FTS5 syntax supports AND, OR, NOT, \"exact phrases\", and prefix*."

    if not results:
        return f"No chats found matching '{query}'."

    lines = [f"Found {total} chats matching '{query}' (showing {len(results)}):\n"]
    for chat in results:
        lines.append(_chat_summary_line(chat))

    if total > offset + limit:
        lines.append(f"\n... {total - offset - limit} more results. Use offset={offset + limit} to see next page.")

    return "\n".join(lines)


@mcp.tool()
def list_workspaces() -> str:
    """List all workspaces in the archive.

    Workspaces represent project directories that Cursor was opened in.
    Each workspace may contain multiple chat conversations.
    """
    db = _get_db()
    workspaces = db.list_workspaces()

    if not workspaces:
        return "No workspaces found in the archive."

    lines = [f"Found {len(workspaces)} workspaces:\n"]
    for ws in workspaces:
        path = ws.get("resolved_path") or ws.get("folder_uri") or ws.get("workspace_hash")
        project = ws.get("project_name")
        chat_count = ws.get("chat_count", 0)
        ws_id = ws.get("id")
        last_seen = _format_datetime(ws.get("last_seen_at"))

        parts = [f"[{ws_id}] {path}"]
        parts.append(f"chats={chat_count}")
        parts.append(f"last_seen={last_seen}")
        if project:
            parts.append(f"project={project}")
        lines.append(" | ".join(parts))

    return "\n".join(lines)


@mcp.tool()
def list_tags() -> str:
    """List all tags and their frequency across chats.

    Tags are labels applied to chats (auto-generated or manual).
    Use find_chats_by_tag to see chats with a specific tag.
    """
    db = _get_db()
    tags = db.get_all_tags()

    if not tags:
        return "No tags found in the archive."

    lines = [f"Found {len(tags)} unique tags:\n"]
    for tag, count in tags.items():
        lines.append(f"  {tag} ({count} chats)")

    return "\n".join(lines)


@mcp.tool()
def find_chats_by_tag(tag: str) -> str:
    """Find all chats with a specific tag.

    Returns chat summaries for all chats that have the given tag.
    Supports SQL LIKE wildcards (% for any characters).

    Args:
        tag: Tag to search for. Use % as wildcard (e.g. "python%" matches "python", "python-api").
    """
    db = _get_db()
    chat_ids = db.find_chats_by_tag(tag)

    if not chat_ids:
        return f"No chats found with tag '{tag}'."

    lines = [f"Found {len(chat_ids)} chats with tag '{tag}':\n"]
    for chat_id in chat_ids:
        chat = db.get_chat(chat_id)
        if chat:
            lines.append(_chat_summary_line(chat))

    return "\n".join(lines)


@mcp.tool()
def get_archive_stats() -> str:
    """Get summary statistics about the chat archive.

    Returns counts of chats, workspaces, messages, tags, and other
    aggregate information. Useful for understanding the scope of the archive.
    """
    db = _get_db()

    total_chats = db.count_chats()
    non_empty = db.count_chats(empty_filter="non_empty")
    empty = db.count_chats(empty_filter="empty")
    workspaces = db.list_workspaces()
    tags = db.get_all_tags()
    last_updated = db.get_last_updated_at()
    filter_options = db.get_filter_options()

    lines = [
        "# Chat Archive Statistics\n",
        f"**Total chats:** {total_chats}",
        f"**With messages:** {non_empty}",
        f"**Empty (no messages):** {empty}",
        f"**Workspaces:** {len(workspaces)}",
        f"**Unique tags:** {len(tags)}",
        f"**Last updated:** {last_updated.strftime('%Y-%m-%d %H:%M') if last_updated else 'never'}",
    ]

    sources = filter_options.get("sources", [])
    if sources:
        lines.append("\n**Sources:**")
        for s in sources:
            lines.append(f"  - {s['value']}: {s['count']} chats")

    modes = filter_options.get("modes", [])
    if modes:
        lines.append("\n**Chat modes:**")
        for m in modes:
            lines.append(f"  - {m['value']}: {m['count']} chats")

    if tags:
        top_tags = list(tags.items())[:10]
        lines.append("\n**Top 10 tags:**")
        for tag, count in top_tags:
            lines.append(f"  - {tag}: {count} chats")

    return "\n".join(lines)


@mcp.tool()
def list_projects() -> str:
    """List all projects in the archive.

    Projects are user-defined groupings of workspaces.
    """
    db = _get_db()
    projects = db.list_projects()

    if not projects:
        return "No projects found in the archive."

    lines = [f"Found {len(projects)} projects:\n"]
    for proj in projects:
        parts = [f"[{proj['id']}] {proj['name']}"]
        if proj.get("description"):
            parts.append(proj["description"])
        lines.append(" | ".join(parts))

    return "\n".join(lines)


def run_server(db_path: Optional[str] = None, transport: str = "stdio"):
    """
    Start the MCP server.

    Parameters
    ----------
    db_path : str, optional
        Path to the chatrxiv database. Uses OS default if not provided.
    transport : str
        Transport protocol: "stdio" (default) or "sse".
    """
    global _db

    if db_path:
        _db = Database(db_path)
        logger.info("MCP server using database: %s", db_path)

    mcp.run(transport=transport)
