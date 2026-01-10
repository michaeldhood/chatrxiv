"""
Chats API routes.
"""

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import get_db
from src.api.schemas import (
    ChatDetail,
    ChatsResponse,
    ChatSummary,
    FilterOption,
    FilterOptionsResponse,
    PlanInfo,
)
from src.core.db import ChatDatabase
from src.services.search import ChatSearchService

router = APIRouter()


def classify_tool_call(msg: Dict[str, Any]) -> Dict[str, str]:
    """
    Classify a tool call by its type based on raw_json content.

    Returns a dict with:
    - tool_type: 'terminal', 'file-read', 'file-write', 'plan', or 'tool-call'
    - tool_name: Human-readable name of the tool
    - tool_description: Brief description of what it does

    Parameters
    ----
    msg : Dict[str, Any]
        Message dictionary containing tool call information

    Returns
    ----
    Dict[str, str]
        Classification with tool_type, tool_name, and tool_description
    """
    raw_json = msg.get("raw_json") or {}

    # Try to extract tool information from various possible fields
    tool_calls = raw_json.get("toolCalls") or raw_json.get("toolCall") or []
    if isinstance(tool_calls, dict):
        tool_calls = [tool_calls]

    tool_former_result = raw_json.get("toolFormerResult") or {}
    code_block = raw_json.get("codeBlock") or {}

    # Check for specific tool types
    tool_type = "tool-call"
    tool_name = "Tool Call"
    tool_description = ""

    # Check toolCalls array for tool names
    for tc in tool_calls:
        name = tc.get("name", "").lower() if isinstance(tc, dict) else str(tc).lower()

        # Plan/Todo tools (check first - "todowrite" contains "write" so must be checked before write)
        if any(kw in name for kw in ["todo", "plan", "task"]):
            tool_type = "plan"
            tool_name = "Plan/Todo"
            break

        # Terminal/Shell tools
        if any(
            kw in name for kw in ["shell", "terminal", "run", "command", "exec", "bash"]
        ):
            tool_type = "terminal"
            tool_name = "Terminal Command"
            if isinstance(tc, dict):
                params = tc.get("parameters") or tc.get("arguments") or {}
                if isinstance(params, dict):
                    cmd = params.get("command", "")
                    if cmd:
                        tool_description = cmd[:100] + ("..." if len(cmd) > 100 else "")
            break

        # File write tools
        if any(
            kw in name
            for kw in ["write", "strreplace", "edit", "create", "save", "editnotebook"]
        ):
            tool_type = "file-write"
            tool_name = "File Write"
            if isinstance(tc, dict):
                params = tc.get("parameters") or tc.get("arguments") or {}
                if isinstance(params, dict):
                    path = params.get("path", "") or params.get("file", "")
                    if path:
                        tool_description = path
            break

        # File read tools
        if any(
            kw in name
            for kw in ["read", "grep", "glob", "search", "find", "ls", "list"]
        ):
            tool_type = "file-read"
            tool_name = "File Read"
            if isinstance(tc, dict):
                params = tc.get("parameters") or tc.get("arguments") or {}
                if isinstance(params, dict):
                    path = (
                        params.get("path", "")
                        or params.get("pattern", "")
                        or params.get("target_directory", "")
                    )
                    if path:
                        tool_description = path
            break

    # Check toolFormerResult for additional context
    if tool_type == "tool-call" and tool_former_result:
        result_type = tool_former_result.get("type", "").lower()
        if "terminal" in result_type or "shell" in result_type:
            tool_type = "terminal"
            tool_name = "Terminal Command"
        elif "file" in result_type:
            if "write" in result_type or "edit" in result_type:
                tool_type = "file-write"
                tool_name = "File Write"
            else:
                tool_type = "file-read"
                tool_name = "File Read"

    # Check codeBlock for file operations
    if tool_type == "tool-call" and code_block:
        uri = code_block.get("uri", "")
        if uri:
            # Code block usually indicates file operation
            tool_type = "file-write"
            tool_name = "File Edit"
            tool_description = uri

    return {
        "tool_type": tool_type,
        "tool_name": tool_name,
        "tool_description": tool_description,
    }


def check_if_todo_message(msg: Dict[str, Any]) -> bool:
    """
    Check if a message contains todo/task list content.

    Todos can be identified by:
    - Task checkboxes (- [ ], - [x])
    - TODO/task keywords
    - Numbered task lists

    Parameters
    ----
    msg : Dict[str, Any]
        Message dictionary to check

    Returns
    ----
    bool
        True if message appears to contain todos/tasks
    """
    text = msg.get("text", "") or msg.get("rich_text", "") or ""
    text_lower = text.lower()

    # Check for common todo/task patterns in content
    todo_patterns = [
        "- [ ]",
        "- [x]",  # Task checkboxes
        "todo:",
        "task:",
        "1. ",
        "2. ",
        "3. ",  # Numbered steps (with at least 3)
    ]

    # Count how many todo indicators are present
    indicator_count = sum(1 for pattern in todo_patterns if pattern in text_lower)

    # If multiple indicators, likely contains todos
    return indicator_count >= 2


def build_tool_group_summary(
    tool_calls: List[Dict[str, Any]],
) -> Tuple[List[str], Optional[str]]:
    """
    Build content types list and summary string for a tool call group.

    Parameters
    ----
    tool_calls : List[Dict[str, Any]]
        List of tool call messages

    Returns
    ----
    Tuple[List[str], Optional[str]]
        Tuple of (content_types list, summary string or None)
    """
    content_types = list(set(tc.get("tool_type", "tool-call") for tc in tool_calls))
    type_counts = {}
    for tc in tool_calls:
        t = tc.get("tool_type", "tool-call")
        type_counts[t] = type_counts.get(t, 0) + 1

    summary_parts = []
    for key, label in [
        ("terminal", "terminal"),
        ("file-write", "write"),
        ("file-read", "read"),
        ("plan", "plan"),
    ]:
        if type_counts.get(key):
            summary_parts.append(f"{type_counts[key]} {label}")

    return content_types, ", ".join(summary_parts) if summary_parts else None


@router.get("/chats", response_model=ChatsResponse)
def get_chats(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    filter: Optional[str] = Query(None, alias="filter"),
    db: ChatDatabase = Depends(get_db),
):
    """
    Get paginated list of chats.

    Parameters
    ----
    page : int
        Page number (1-indexed)
    limit : int
        Results per page (max 100)
    filter : str, optional
        Filter by empty status: 'empty', 'non_empty', or None (all)
    db : ChatDatabase
        Database instance (injected via dependency)
    """
    search_service = ChatSearchService(db)

    offset = (page - 1) * limit
    empty_filter = filter  # 'empty', 'non_empty', or None

    chats = search_service.list_chats(
        limit=limit, offset=offset, empty_filter=empty_filter
    )
    total = search_service.count_chats(empty_filter=empty_filter)

    return ChatsResponse(
        chats=[ChatSummary(**chat) for chat in chats],
        total=total,
        page=page,
        limit=limit,
        filter=empty_filter,
    )


@router.get("/chats/{chat_id}", response_model=ChatDetail)
def get_chat(chat_id: int, db: ChatDatabase = Depends(get_db)):
    """
    Get a specific chat by ID with all messages.

    Parameters
    ----
    chat_id : int
        Chat ID
    db : ChatDatabase
        Database instance (injected via dependency)
    """
    search_service = ChatSearchService(db)
    chat = search_service.get_chat(chat_id)

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Get plans linked to this chat
    plans_data = db.get_plans_for_chat(chat_id)
    chat["plans"] = [PlanInfo(**plan) for plan in plans_data]

    # Process messages - group tool calls together and classify them
    # Frontend expects this for collapsible tool call groups with filtering
    processed_messages = []
    tool_call_group = []

    for msg in chat.get("messages", []):
        msg_type = msg.get("message_type", "response")

        # Skip empty messages
        if msg_type == "empty":
            continue

        # Group consecutive tool calls
        if msg_type == "tool_call":
            # Classify the tool call
            classification = classify_tool_call(msg)
            msg["tool_type"] = classification["tool_type"]
            msg["tool_name"] = classification["tool_name"]
            msg["tool_description"] = classification["tool_description"]

            tool_call_group.append(msg)
        else:
            # If we have accumulated tool calls, add them as a group
            if tool_call_group:
                content_types, summary = build_tool_group_summary(tool_call_group)
                processed_messages.append(
                    {
                        "type": "tool_call_group",
                        "tool_calls": tool_call_group.copy(),
                        "content_types": content_types,
                        "summary": summary,
                    }
                )
                tool_call_group = []

            # Check if this is a thinking message
            if msg_type == "thinking":
                msg["is_thinking"] = True

            # Check if this message contains todos/tasks
            msg["is_todo"] = check_if_todo_message(msg)

            # Add the current message
            processed_messages.append({"type": "message", "data": msg})

    # Don't forget remaining tool calls
    if tool_call_group:
        content_types, summary = build_tool_group_summary(tool_call_group)
        processed_messages.append(
            {
                "type": "tool_call_group",
                "tool_calls": tool_call_group,
                "content_types": content_types,
                "summary": summary,
            }
        )

    chat["processed_messages"] = processed_messages

    return ChatDetail(**chat)


@router.get("/filter-options", response_model=FilterOptionsResponse)
def get_filter_options(db: ChatDatabase = Depends(get_db)):
    """
    Get all available filter options (sources, modes) with counts.

    Used to populate filter dropdowns in the UI. Returns all distinct
    values regardless of current pagination.

    Parameters
    ----
    db : ChatDatabase
        Database instance (injected via dependency)
    """
    options = db.get_filter_options()
    return FilterOptionsResponse(
        sources=[FilterOption(**s) for s in options["sources"]],
        modes=[FilterOption(**m) for m in options["modes"]],
    )
