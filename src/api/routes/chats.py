"""
Chats API routes.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status

logger = logging.getLogger(__name__)

from src.api.deps import get_db
from src.api.routes.chat_processing import select_processed_window
from src.api.schemas import (
    BulkChatsRequest,
    BulkChatsResponse,
    ChatDetail,
    ChatsResponse,
    ChatSummary,
    FilterOption,
    FilterOptionsResponse,
    PlanInfo,
)
from src.core.db import ChatDatabase
from src.services.search import ChatSearchService
from src.services.summarizer import ChatSummarizer

router = APIRouter()


TERMINAL_TOOL_KEYWORDS = ("shell", "terminal", "run", "command", "exec", "bash")
PLAN_TOOL_KEYWORDS = ("todo", "plan", "task")
FILE_WRITE_TOOL_KEYWORDS = ("write", "strreplace", "edit", "create", "save", "editnotebook")
FILE_READ_TOOL_KEYWORDS = ("read", "grep", "glob", "search", "find", "ls", "list")


def _ensure_dict(value: Any) -> Dict[str, Any]:
    """Best-effort conversion of JSON-like payloads to dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _normalize_tool_calls(raw_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalize tool-call arrays across Cursor and Claude Code formats.

    Supported keys:
    - Cursor: toolCalls / toolCall
    - Claude Code: tool_calls
    """
    candidates = (
        raw_json.get("toolCalls")
        or raw_json.get("toolCall")
        or raw_json.get("tool_calls")
        or []
    )
    if isinstance(candidates, dict):
        candidates = [candidates]
    if not isinstance(candidates, list):
        return []
    return [tc for tc in candidates if isinstance(tc, dict)]


def _extract_tool_params(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """Extract params/arguments/input payload from a tool call dict."""
    params = (
        tool_call.get("parameters")
        or tool_call.get("arguments")
        or tool_call.get("params")
        or tool_call.get("input")
        or {}
    )
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except (json.JSONDecodeError, TypeError):
            params = {}
    return params if isinstance(params, dict) else {}


def _extract_command_from_params(params: Dict[str, Any]) -> str:
    """Extract terminal command string from a tool parameter payload."""
    if not isinstance(params, dict):
        return ""
    command = (
        params.get("command")
        or params.get("cmd")
        or params.get("script")
        or ""
    )
    return command if isinstance(command, str) else str(command)


def _is_terminal_tool_name(name: str) -> bool:
    """Heuristic terminal tool-name check used across sources."""
    normalized = (name or "").lower()
    return any(kw in normalized for kw in TERMINAL_TOOL_KEYWORDS)


def _extract_tool_result_text(content: Any) -> str:
    """Normalize tool_result content (string/list/dict) to plain text."""
    if isinstance(content, str):
        return content

    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
        return json.dumps(content, ensure_ascii=False)

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif item:
                    parts.append(json.dumps(item, ensure_ascii=False))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)

    return str(content) if content is not None else ""


def extract_file_paths_from_tool_calls(raw_json: Dict[str, Any]) -> List[str]:
    """Extract likely file paths referenced by tool calls across sources."""
    raw_json = _ensure_dict(raw_json)
    paths: List[str] = []
    for tc in _normalize_tool_calls(raw_json):
        params = _extract_tool_params(tc)
        for key in ("path", "file", "target_notebook", "uri"):
            value = params.get(key)
            if isinstance(value, str) and value:
                paths.append(value)
    return paths


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
    raw_json = _ensure_dict(msg.get("raw_json") or {})
    tool_calls = _normalize_tool_calls(raw_json)

    tool_former_result = raw_json.get("toolFormerResult") or {}
    code_block = raw_json.get("codeBlock") or {}

    # Check for specific tool types
    tool_type = "tool-call"
    tool_name = "Tool Call"
    tool_description = ""

    # Check toolCalls array for tool names
    for tc in tool_calls:
        name = (tc.get("name") or "").lower()
        params = _extract_tool_params(tc)

        # Plan/Todo tools (check first - "todowrite" contains "write" so must be checked before write)
        if any(kw in name for kw in PLAN_TOOL_KEYWORDS):
            tool_type = "plan"
            tool_name = "Plan/Todo"
            break

        # Terminal/Shell tools
        if _is_terminal_tool_name(name):
            tool_type = "terminal"
            tool_name = "Terminal Command"
            cmd = _extract_command_from_params(params)
            if cmd:
                tool_description = cmd[:100] + ("..." if len(cmd) > 100 else "")
            break

        # File write tools
        if any(kw in name for kw in FILE_WRITE_TOOL_KEYWORDS):
            tool_type = "file-write"
            tool_name = "File Write"
            path = (
                params.get("path", "")
                or params.get("file", "")
                or params.get("target_notebook", "")
                or params.get("uri", "")
            )
            if isinstance(path, str) and path:
                tool_description = path
            break

        # File read tools
        if any(kw in name for kw in FILE_READ_TOOL_KEYWORDS):
            tool_type = "file-read"
            tool_name = "File Read"
            path = (
                params.get("path", "")
                or params.get("pattern", "")
                or params.get("target_directory", "")
                or params.get("file", "")
            )
            if isinstance(path, str) and path:
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


def extract_plan_content(raw_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract plan content from create_plan tool call bubble.

    Parameters
    ----
    raw_json : Dict[str, Any]
        Raw JSON data from message bubble

    Returns
    ----
    Optional[Dict[str, Any]]
        Plan content dict with name, overview, content, todos, uri, status
        or None if not a create_plan tool call
    """
    if not raw_json:
        return None

    tool_former = raw_json.get("toolFormerData", {})
    if not tool_former or tool_former.get("name") != "create_plan":
        return None

    # Parse rawArgs or params (both contain the plan)
    raw_args = tool_former.get("rawArgs", "{}")
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            raw_args = {}

    # Fallback to params if rawArgs parsing failed
    if not raw_args:
        params = tool_former.get("params", "{}")
        if isinstance(params, str):
            try:
                raw_args = json.loads(params)
            except (json.JSONDecodeError, TypeError):
                raw_args = {}
        else:
            raw_args = params or {}

    additional = tool_former.get("additionalData", {})

    return {
        "name": raw_args.get("name") or additional.get("pinnedName") or "Untitled Plan",
        "overview": raw_args.get("overview"),
        "content": raw_args.get("plan"),  # Full markdown
        "todos": raw_args.get("todos", []),
        "uri": additional.get("planUri"),
        "status": tool_former.get("status"),  # completed, etc.
    }


def _extract_cursor_terminal_command(
    raw_json: Dict[str, Any], created_at: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Extract terminal command payload from Cursor run_terminal_cmd bubbles."""
    # Try multiple possible key names for toolFormerData (case variations, etc.)
    tool_former = (
        raw_json.get("toolFormerData")
        or raw_json.get("tool_former_data")
        or raw_json.get("toolFormer")
        or {}
    )
    tool_former = _ensure_dict(tool_former)

    if not tool_former or tool_former.get("name") != "run_terminal_cmd":
        return None

    # Parse rawArgs or params to get the command
    raw_args = _ensure_dict(tool_former.get("rawArgs", {}))
    params_dict = _ensure_dict(tool_former.get("params", {}))

    command = _extract_command_from_params(raw_args) or _extract_command_from_params(params_dict)

    # Parse result to get output
    result = _ensure_dict(tool_former.get("result", {}))
    output = result.get("output", "")
    status = tool_former.get("status")

    if not command or not command.strip():
        return None

    return {
        "command": command,
        "output": output if isinstance(output, str) else str(output),
        "status": status,
        "created_at": created_at,
        "tool_use_id": None,
    }


def extract_terminal_commands(
    raw_json: Dict[str, Any], created_at: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extract terminal commands across Cursor and Claude Code formats.

    Returns a list because Claude Code assistant messages may include multiple tool calls.
    """
    raw_json = _ensure_dict(raw_json)
    if not raw_json:
        return []

    commands: List[Dict[str, Any]] = []

    # Cursor format (toolFormerData/run_terminal_cmd)
    cursor_cmd = _extract_cursor_terminal_command(raw_json, created_at=created_at)
    if cursor_cmd:
        commands.append(cursor_cmd)

    # Claude Code format (tool_calls with name/input)
    for tc in _normalize_tool_calls(raw_json):
        name = tc.get("name", "")
        if not _is_terminal_tool_name(name):
            continue

        params = _extract_tool_params(tc)
        command = _extract_command_from_params(params)
        if not command.strip():
            continue

        commands.append(
            {
                "command": command,
                "output": "",
                "status": tc.get("status"),
                "created_at": created_at,
                "tool_use_id": tc.get("id") or tc.get("tool_use_id"),
            }
        )

    # Deduplicate by (tool_use_id, command)
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for cmd in commands:
        key = (cmd.get("tool_use_id"), cmd.get("command"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cmd)

    return deduped


def extract_terminal_command(
    raw_json: Dict[str, Any], created_at: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Backward-compatible single-command wrapper.
    """
    commands = extract_terminal_commands(raw_json, created_at=created_at)
    return commands[0] if commands else None


def extract_terminal_result_blocks(raw_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract terminal outputs from Claude Code tool_result blocks.
    """
    raw_json = _ensure_dict(raw_json)
    if not raw_json:
        return []

    tool_results = raw_json.get("tool_results") or []
    if not isinstance(tool_results, list):
        tool_results = []

    # Backward compatibility: parse from content_blocks if tool_results not materialized.
    if not tool_results:
        content_blocks = raw_json.get("content_blocks") or []
        if isinstance(content_blocks, list):
            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_results.append(
                        {
                            "tool_use_id": block.get("tool_use_id"),
                            "content": block.get("content"),
                            "is_error": bool(block.get("is_error", False)),
                        }
                    )

    results: List[Dict[str, Any]] = []
    for result in tool_results:
        if not isinstance(result, dict):
            continue
        output = _extract_tool_result_text(result.get("content", ""))
        if not output.strip():
            continue
        status = "error" if result.get("is_error") else "completed"
        results.append(
            {
                "tool_use_id": result.get("tool_use_id"),
                "output": output,
                "status": status,
            }
        )

    return results


def is_terminal_only_tool_message(raw_json: Dict[str, Any]) -> bool:
    """
    Check whether a tool_call message should render only as terminal command(s).
    """
    raw_json = _ensure_dict(raw_json)
    if not raw_json:
        return False

    # Cursor run_terminal_cmd
    cursor_tool_former = _ensure_dict(
        raw_json.get("toolFormerData")
        or raw_json.get("tool_former_data")
        or raw_json.get("toolFormer")
        or {}
    )
    if cursor_tool_former.get("name") == "run_terminal_cmd":
        return True

    # Claude Code assistant tool calls
    tool_calls = _normalize_tool_calls(raw_json)
    if tool_calls:
        names = [(tc.get("name") or "") for tc in tool_calls]
        if names and all(_is_terminal_tool_name(name) for name in names):
            return True

    # Claude Code tool result blocks (paired output for terminal calls)
    if extract_terminal_result_blocks(raw_json):
        return True

    return False


def extract_tool_result(raw_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract tool result from toolFormerData.

    Parameters
    ----
    raw_json : Dict[str, Any]
        Raw JSON data from message bubble

    Returns
    ----
    Optional[Dict[str, Any]]
        Tool result dict with output, contents, diff, matches, etc.
        or None if no toolFormerData present
    """
    tool_former = raw_json.get("toolFormerData", {})
    if not tool_former:
        return None

    result_str = tool_former.get("result", "{}")
    if isinstance(result_str, str):
        try:
            result = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            result = {}
    else:
        result = result_str or {}

    tool_name = tool_former.get("name", "")
    status = tool_former.get("status")

    # Normalize top_files for grep results - ensure it's always a valid array
    top_files_raw = result.get("topFiles") or result.get("top_files") or []
    if not isinstance(top_files_raw, list):
        top_files_raw = []

    # Normalize structure - handle both camelCase and snake_case
    top_files = []
    for item in top_files_raw:
        if isinstance(item, dict):
            normalized = {
                "uri": item.get("uri") or item.get("file") or item.get("path") or "",
                "matchCount": item.get("matchCount")
                or item.get("match_count")
                or item.get("count")
                or 0,
            }
            if normalized["uri"]:  # Only add if we have a URI
                top_files.append(normalized)

    return {
        "tool_name": tool_name,
        "status": status,
        "output": result.get("output"),  # Terminal
        "contents": result.get("contents"),  # File read
        "diff": result.get("diff"),  # File write
        "total_matches": result.get("totalMatches"),  # Grep
        "top_files": top_files,  # Grep - normalized array
        "error": result.get("error") or result.get("rejected"),
    }


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


@router.post("/chats/bulk", response_model=BulkChatsResponse)
def get_chats_bulk(
    body: BulkChatsRequest,
    db: ChatDatabase = Depends(get_db),
):
    """
    Fetch multiple chats by ID in a single request.

    Returns full chat details (with messages) for each requested chat.
    Chats are returned in the same order as the requested IDs.
    IDs that don't exist are silently skipped.

    Parameters
    ----------
    body : BulkChatsRequest
        Request body containing chat_ids (1-100 IDs)
    db : ChatDatabase
        Database instance (injected via dependency)
    """
    chats = db.get_chats_bulk(body.chat_ids)

    return BulkChatsResponse(
        chats=[ChatDetail(**chat) for chat in chats],
        requested=len(body.chat_ids),
        found=len(chats),
    )


@router.get("/chats/{chat_id}", response_model=ChatDetail)
def get_chat(
    chat_id: int,
    message_offset: int = Query(0, ge=0),
    message_limit: Optional[int] = Query(None, ge=1, le=200),
    db: ChatDatabase = Depends(get_db),
):
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

    total_messages = chat.get("total_messages")
    if total_messages is None:
        total_messages = len(chat.get("messages", []))

    # Get plans linked to this chat
    plans_data = db.get_plans_for_chat(chat_id)
    chat["plans"] = [PlanInfo(**plan) for plan in plans_data]

    # Build map of plan file paths to plan info for quick lookup
    plans_by_file_path = {}
    created_plans = [p for p in plans_data if p.get("relationship") == "created"]
    for plan in created_plans:
        if plan.get("file_path"):
            plans_by_file_path[plan["file_path"]] = plan

    # Process messages - group tool calls together and classify them
    # Frontend expects this for collapsible tool call groups with filtering
    processed_messages = []
    tool_call_group = []
    tool_call_group_start: Optional[int] = None
    tool_call_group_end: Optional[int] = None
    pending_plan_content = None  # Track plan content to insert after tool call group
    pending_terminal_commands = []  # Track terminal commands to insert after tool call group
    pending_terminal_by_tool_use_id = {}  # Claude Code tool_use_id -> terminal command

    def append_processed_item(item: Dict[str, Any], start: int, end: int) -> None:
        item["source_span"] = {"start": start, "end": end}
        processed_messages.append(item)

    for raw_index, msg in enumerate(chat.get("messages", [])):
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

            # Extract plan content if this is a create_plan tool call
            raw_json = _ensure_dict(msg.get("raw_json") or {})
            plan_content = extract_plan_content(raw_json)
            if plan_content:
                # Store plan content to insert after tool call group
                pending_plan_content = plan_content

            # Extract terminal commands across source formats
            created_at = msg.get("created_at")
            terminal_commands = extract_terminal_commands(raw_json, created_at)
            terminal_results = extract_terminal_result_blocks(raw_json)

            for terminal_command in terminal_commands:
                tool_use_id = terminal_command.get("tool_use_id")
                terminal_command["_span_start"] = raw_index
                terminal_command["_span_end"] = raw_index + 1
                if tool_use_id:
                    pending_terminal_by_tool_use_id[tool_use_id] = terminal_command
                else:
                    pending_terminal_commands.append(terminal_command)
                logger.debug(
                    f"get_chat: extracted terminal command '{terminal_command.get('command', '')[:50]}...' "
                    f"for message bubble_id={msg.get('bubble_id')}"
                )

            # Pair Claude Code tool_result output with prior terminal tool_use
            for terminal_result in terminal_results:
                tool_use_id = terminal_result.get("tool_use_id")
                if tool_use_id and tool_use_id in pending_terminal_by_tool_use_id:
                    matched = pending_terminal_by_tool_use_id.pop(tool_use_id)
                    matched["output"] = terminal_result.get("output", matched.get("output", ""))
                    matched["status"] = terminal_result.get("status") or matched.get("status")
                    matched["_span_end"] = raw_index + 1
                    pending_terminal_commands.append(matched)
                    continue

                # Fallback for orphaned tool results
                if terminal_result.get("output"):
                    pending_terminal_commands.append(
                        {
                            "command": "[Terminal output]",
                            "output": terminal_result.get("output", ""),
                            "status": terminal_result.get("status"),
                            "created_at": created_at,
                            "tool_use_id": tool_use_id,
                            "_span_start": raw_index,
                            "_span_end": raw_index + 1,
                        }
                    )

            # Terminal-only tool calls/results should render as standalone terminal blocks
            if is_terminal_only_tool_message(raw_json):
                continue

            # Extract tool result (output, contents, etc.)
            tool_result = extract_tool_result(raw_json)
            if tool_result:
                msg["tool_result"] = tool_result

            if tool_call_group_start is None:
                tool_call_group_start = raw_index
            tool_call_group_end = raw_index + 1
            tool_call_group.append(msg)
        else:
            # Flush pending terminal commands even if there is no tool_call_group
            if pending_terminal_by_tool_use_id:
                pending_terminal_commands.extend(pending_terminal_by_tool_use_id.values())
                pending_terminal_by_tool_use_id = {}
            if pending_terminal_commands and not tool_call_group:
                for terminal_cmd in pending_terminal_commands:
                    terminal_cmd.pop("tool_use_id", None)
                    span_start = terminal_cmd.pop("_span_start", raw_index)
                    span_end = terminal_cmd.pop("_span_end", span_start + 1)
                    append_processed_item(
                        {
                            "type": "terminal_command",
                            "terminal_command": terminal_cmd,
                        },
                        span_start,
                        span_end,
                    )
                pending_terminal_commands = []

            # If we have accumulated tool calls, add them as a group
            if tool_call_group:
                content_types, summary = build_tool_group_summary(tool_call_group)
                group_start = tool_call_group_start or raw_index
                group_end = tool_call_group_end or (group_start + 1)
                append_processed_item(
                    {
                        "type": "tool_call_group",
                        "tool_calls": tool_call_group.copy(),
                        "content_types": content_types,
                        "summary": summary,
                    },
                    group_start,
                    group_end,
                )

                # Insert plan content right after the tool call group if we have one
                if pending_plan_content:
                    append_processed_item(
                        {
                            "type": "plan_content",
                            "plan": pending_plan_content,
                        },
                        group_start,
                        group_end,
                    )
                    pending_plan_content = None

                # Insert terminal commands right after the tool call group
                if pending_terminal_by_tool_use_id:
                    pending_terminal_commands.extend(pending_terminal_by_tool_use_id.values())
                    pending_terminal_by_tool_use_id = {}
                if pending_terminal_commands:
                    logger.debug(
                        f"get_chat: inserting {len(pending_terminal_commands)} terminal command(s) "
                        f"after tool call group"
                    )
                for terminal_cmd in pending_terminal_commands:
                    terminal_cmd.pop("tool_use_id", None)
                    span_start = terminal_cmd.pop("_span_start", group_start)
                    span_end = terminal_cmd.pop("_span_end", group_end)
                    append_processed_item(
                        {
                            "type": "terminal_command",
                            "terminal_command": terminal_cmd,
                        },
                        span_start,
                        span_end,
                    )
                pending_terminal_commands = []

                # Check if this tool call group created any plans
                # Look for file write operations that match plan file paths
                for tool_msg in tool_call_group:
                    # Check tool_description (from classification)
                    tool_desc = tool_msg.get("tool_description", "")
                    # Also check raw_json for actual file path in parameters
                    raw_json = _ensure_dict(tool_msg.get("raw_json", {}))

                    # Extract file paths from tool call parameters
                    file_paths_to_check = [tool_desc] if tool_desc else []
                    file_paths_to_check.extend(extract_file_paths_from_tool_calls(raw_json))

                    # Check if any path matches a plan file
                    for file_path in file_paths_to_check:
                        if file_path and ".plan.md" in file_path:
                            # Check if this path matches any created plan
                            for plan_file_path, plan_info in list(
                                plans_by_file_path.items()
                            ):
                                # Match if plan path is in tool path or vice versa
                                if plan_file_path and (
                                    plan_file_path in file_path
                                    or file_path in plan_file_path
                                    or plan_file_path.endswith(file_path)
                                    or file_path.endswith(plan_file_path)
                                ):
                                    # Insert plan creation indicator after this tool group
                                    append_processed_item(
                                        {
                                            "type": "plan_created",
                                            "plan": {
                                                "id": plan_info["id"],
                                                "plan_id": plan_info["plan_id"],
                                                "name": plan_info["name"],
                                                "file_path": plan_info.get("file_path"),
                                                "created_at": plan_info.get(
                                                    "created_at"
                                                ),
                                            },
                                        },
                                        group_start,
                                        group_end,
                                    )
                                    # Remove from map to avoid duplicate indicators
                                    del plans_by_file_path[plan_file_path]
                                    break

                tool_call_group = []
                tool_call_group_start = None
                tool_call_group_end = None

            # Check if this is a thinking message
            if msg_type == "thinking":
                msg["is_thinking"] = True

            # Add the current message
            append_processed_item({"type": "message", "data": msg}, raw_index, raw_index + 1)

    # Don't forget remaining tool calls
    if tool_call_group:
        content_types, summary = build_tool_group_summary(tool_call_group)
        group_start = tool_call_group_start or 0
        group_end = tool_call_group_end or (group_start + 1)
        append_processed_item(
            {
                "type": "tool_call_group",
                "tool_calls": tool_call_group,
                "content_types": content_types,
                "summary": summary,
            },
            group_start,
            group_end,
        )

        # Insert plan content right after the final tool call group if we have one
        if pending_plan_content:
            append_processed_item(
                {
                    "type": "plan_content",
                    "plan": pending_plan_content,
                },
                group_start,
                group_end,
            )
            pending_plan_content = None

        # Insert terminal commands right after the final tool call group
        if pending_terminal_by_tool_use_id:
            pending_terminal_commands.extend(pending_terminal_by_tool_use_id.values())
            pending_terminal_by_tool_use_id = {}
        if pending_terminal_commands:
            logger.debug(
                f"get_chat: inserting {len(pending_terminal_commands)} terminal command(s) "
                f"after final tool call group"
            )
        for terminal_cmd in pending_terminal_commands:
            terminal_cmd.pop("tool_use_id", None)
            span_start = terminal_cmd.pop("_span_start", group_start)
            span_end = terminal_cmd.pop("_span_end", group_end)
            append_processed_item(
                {
                    "type": "terminal_command",
                    "terminal_command": terminal_cmd,
                },
                span_start,
                span_end,
            )
        pending_terminal_commands = []

        # Check if this final tool call group created any plans
        for tool_msg in tool_call_group:
            # Check tool_description (from classification)
            tool_desc = tool_msg.get("tool_description", "")
            # Also check raw_json for actual file path in parameters
            raw_json = _ensure_dict(tool_msg.get("raw_json", {}))

            # Extract file paths from tool call parameters
            file_paths_to_check = [tool_desc] if tool_desc else []
            file_paths_to_check.extend(extract_file_paths_from_tool_calls(raw_json))

            # Check if any path matches a plan file
            for file_path in file_paths_to_check:
                if file_path and ".plan.md" in file_path:
                    for plan_file_path, plan_info in list(plans_by_file_path.items()):
                        # Match if plan path is in tool path or vice versa
                        if plan_file_path and (
                            plan_file_path in file_path
                            or file_path in plan_file_path
                            or plan_file_path.endswith(file_path)
                            or file_path.endswith(plan_file_path)
                        ):
                            append_processed_item(
                                {
                                    "type": "plan_created",
                                    "plan": {
                                        "id": plan_info["id"],
                                        "plan_id": plan_info["plan_id"],
                                        "name": plan_info["name"],
                                        "file_path": plan_info.get("file_path"),
                                        "created_at": plan_info.get("created_at"),
                                    },
                                },
                                group_start,
                                group_end,
                            )
                            del plans_by_file_path[plan_file_path]
                            break

    # Terminal-only conversations may not have tool_call_group boundaries
    if pending_terminal_by_tool_use_id:
        pending_terminal_commands.extend(pending_terminal_by_tool_use_id.values())
        pending_terminal_by_tool_use_id = {}
    if pending_terminal_commands:
        for terminal_cmd in pending_terminal_commands:
            terminal_cmd.pop("tool_use_id", None)
            span_start = terminal_cmd.pop("_span_start", 0)
            span_end = terminal_cmd.pop("_span_end", span_start + 1)
            append_processed_item(
                {
                    "type": "terminal_command",
                    "terminal_command": terminal_cmd,
                },
                span_start,
                span_end,
            )
        pending_terminal_commands = []

    # If any plans weren't matched to tool calls, add indicators after first message as fallback
    if plans_by_file_path and processed_messages:
        first_span = processed_messages[0].get("source_span", {"start": 0, "end": 1})
        for plan_info in plans_by_file_path.values():
            # Insert after first message
            fallback_item = {
                "type": "plan_created",
                "plan": {
                    "id": plan_info["id"],
                    "plan_id": plan_info["plan_id"],
                    "name": plan_info["name"],
                    "file_path": plan_info.get("file_path"),
                    "created_at": plan_info.get("created_at"),
                },
                "source_span": first_span,
            }
            processed_messages.insert(
                1,
                fallback_item,
            )

    chat["total_messages"] = total_messages

    if message_limit is not None:
        selected_processed, coverage = select_processed_window(
            processed_messages,
            message_offset,
            message_limit,
        )
        covered_start = coverage["covered_start"]
        covered_end = coverage["covered_end"]
        chat["messages"] = chat.get("messages", [])[covered_start:covered_end]
        chat["processed_messages"] = selected_processed
        chat["pagination"] = {
            "requested_offset": message_offset,
            "requested_limit": message_limit,
            "covered_start": covered_start,
            "covered_end": covered_end,
            "has_previous": covered_start > 0,
            "has_more": covered_end < total_messages,
        }
    else:
        chat["processed_messages"] = processed_messages

    # Log summary of processed messages
    processed_for_log = chat["processed_messages"]
    terminal_count = sum(1 for m in processed_for_log if m.get("type") == "terminal_command")
    tool_group_count = sum(1 for m in processed_for_log if m.get("type") == "tool_call_group")
    logger.debug(
        f"get_chat: processed {len(processed_for_log)} messages total: "
        f"{terminal_count} terminal_command items, {tool_group_count} tool_call_groups"
    )

    return ChatDetail(**chat)


@router.post("/chats/{chat_id}/summarize")
def summarize_chat(chat_id: int, db: ChatDatabase = Depends(get_db)):
    """
    Generate and store a summary for a chat using Claude API.

    Parameters
    ----
    chat_id : int
        Chat ID to summarize
    db : ChatDatabase
        Database instance (injected via dependency)

    Returns
    ----
    Dict[str, Any]
        Summary text and metadata

    Raises
    ---
    HTTPException
        404 if chat not found
        500 if summarization fails (API key missing, API error, etc.)
    """
    search_service = ChatSearchService(db)
    chat = search_service.get_chat(chat_id)

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Summarization is not configured",
        )

    try:
        # Initialize summarizer
        summarizer = ChatSummarizer(api_key=api_key)

        # Generate summary
        summary = summarizer.summarize_chat(
            chat_title=chat.get("title") or "Untitled Chat",
            messages=chat.get("messages", []),
            workspace_path=chat.get("workspace_path"),
            created_at=chat.get("created_at"),
        )

        # Store summary in database
        db.update_chat_summary(chat_id, summary)

        return {
            "summary": summary,
            "chat_id": chat_id,
            "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        }

    except ImportError:
        logger.exception("Summarization service import failed for chat %s", chat_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Summarization service is unavailable",
        )
    except ValueError:
        logger.exception("Invalid summarization configuration for chat %s", chat_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Summarization is not configured correctly",
        )
    except Exception:
        logger.exception("Error generating summary for chat %s", chat_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate summary",
        )


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
