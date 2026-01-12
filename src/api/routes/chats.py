"""
Chats API routes.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger(__name__)

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
from src.services.summarizer import ChatSummarizer

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


def extract_terminal_command(
    raw_json: Dict[str, Any], created_at: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extract terminal command and output from run_terminal_cmd tool call bubble.

    Parameters
    ----
    raw_json : Dict[str, Any]
        Raw JSON data from message bubble
    created_at : str, optional
        Timestamp when the command was executed

    Returns
    ----
    Optional[Dict[str, Any]]
        Terminal command dict with command, output, status, created_at
        or None if not a run_terminal_cmd tool call
    """
    if not raw_json:
        logger.debug("extract_terminal_command: raw_json is empty or None")
        return None

    # Handle case where raw_json might be a JSON string (defensive programming)
    if isinstance(raw_json, str):
        try:
            raw_json = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            logger.debug("extract_terminal_command: failed to parse raw_json as JSON string")
            return None

    if not isinstance(raw_json, dict):
        logger.debug(f"extract_terminal_command: raw_json is not a dict, type={type(raw_json)}")
        return None

    # Log raw_json structure for debugging
    raw_json_keys = list(raw_json.keys())
    logger.debug(
        f"extract_terminal_command: raw_json type={type(raw_json)}, keys={raw_json_keys}"
    )

    # Try multiple possible key names for toolFormerData (case variations, etc.)
    tool_former = (
        raw_json.get("toolFormerData")
        or raw_json.get("tool_former_data")
        or raw_json.get("toolFormer")
        or {}
    )
    
    # If tool_former is a string, try to parse it
    if isinstance(tool_former, str):
        try:
            tool_former = json.loads(tool_former)
        except (json.JSONDecodeError, TypeError):
            tool_former = {}
    
    tool_name = tool_former.get("name") if isinstance(tool_former, dict) else None
    logger.debug(
        f"extract_terminal_command: tool_former exists={bool(tool_former)}, "
        f"tool_former type={type(tool_former)}, name={tool_name}"
    )
    
    if not isinstance(tool_former, dict) or tool_former.get("name") != "run_terminal_cmd":
        if tool_former:
            logger.debug(
                f"extract_terminal_command: tool name mismatch - expected 'run_terminal_cmd', "
                f"got '{tool_name}'"
            )
        return None

    # Parse rawArgs or params to get the command
    raw_args = tool_former.get("rawArgs", "{}")
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            raw_args = {}

    # Fallback to params if rawArgs parsing failed
    params_dict = {}
    if not raw_args or "command" not in raw_args:
        params = tool_former.get("params", "{}")
        if isinstance(params, str):
            try:
                params_dict = json.loads(params)
            except (json.JSONDecodeError, TypeError):
                params_dict = {}
        else:
            params_dict = params or {}

        # Extract command from params
        command = params_dict.get("command", "")
        if not command and raw_args:
            command = raw_args.get("command", "")
    else:
        command = raw_args.get("command", "")

    # Parse result to get output
    result_str = tool_former.get("result", "{}")
    if isinstance(result_str, str):
        try:
            result = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            result = {}
    else:
        result = result_str or {}

    output = result.get("output", "")
    status = tool_former.get("status")

    # Only return terminal command if we have a command string
    if not command or not command.strip():
        raw_args_keys = list(raw_args.keys()) if isinstance(raw_args, dict) else "N/A"
        params_keys = list(params_dict.keys()) if isinstance(params_dict, dict) else "N/A"
        logger.debug(
            f"extract_terminal_command: no command found in rawArgs or params, "
            f"rawArgs keys={raw_args_keys}, params keys={params_keys}"
        )
        return None

    logger.debug(
        f"extract_terminal_command: extracted command='{command[:50]}...' "
        f"(len={len(command)}), output_len={len(output)}, status={status}"
    )

    return {
        "command": command,
        "output": output,
        "status": status,
        "created_at": created_at,
    }


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
    tool_call_group_index = -1  # Track index for inserting plan indicators
    pending_plan_content = None  # Track plan content to insert after tool call group
    pending_terminal_commands = []  # Track terminal commands to insert after tool call group

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

            # Extract plan content if this is a create_plan tool call
            raw_json = msg.get("raw_json") or {}
            plan_content = extract_plan_content(raw_json)
            if plan_content:
                # Store plan content to insert after tool call group
                pending_plan_content = plan_content

            # Extract terminal command if this is a run_terminal_cmd tool call
            created_at = msg.get("created_at")
            terminal_command = extract_terminal_command(raw_json, created_at)
            if terminal_command:
                # Store terminal command to insert after tool call group
                # Don't add to tool_call_group - it will be rendered separately
                logger.debug(
                    f"get_chat: extracted terminal command '{terminal_command.get('command', '')[:50]}...' "
                    f"for message bubble_id={msg.get('bubble_id')}"
                )
                pending_terminal_commands.append(terminal_command)
                # Skip adding to tool_call_group - terminal commands render as standalone items
            else:
                # Log why extraction failed for tool_call messages
                if msg_type == "tool_call":
                    tool_former = raw_json.get("toolFormerData", {}) if raw_json else {}
                    tool_name = tool_former.get("name") if tool_former else None
                    logger.debug(
                        f"get_chat: terminal command extraction returned None for "
                        f"tool_call name={tool_name}, bubble_id={msg.get('bubble_id')}"
                    )

                # Extract tool result (output, contents, etc.)
                tool_result = extract_tool_result(raw_json)
                if tool_result:
                    msg["tool_result"] = tool_result

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

                # Insert plan content right after the tool call group if we have one
                if pending_plan_content:
                    processed_messages.append(
                        {
                            "type": "plan_content",
                            "plan": pending_plan_content,
                        }
                    )
                    pending_plan_content = None

                # Insert terminal commands right after the tool call group
                if pending_terminal_commands:
                    logger.debug(
                        f"get_chat: inserting {len(pending_terminal_commands)} terminal command(s) "
                        f"after tool call group"
                    )
                for terminal_cmd in pending_terminal_commands:
                    processed_messages.append(
                        {
                            "type": "terminal_command",
                            "terminal_command": terminal_cmd,
                        }
                    )
                pending_terminal_commands = []

                # Check if this tool call group created any plans
                # Look for file write operations that match plan file paths
                for tool_msg in tool_call_group:
                    # Check tool_description (from classification)
                    tool_desc = tool_msg.get("tool_description", "")
                    # Also check raw_json for actual file path in parameters
                    raw_json = tool_msg.get("raw_json", {})
                    tool_calls = (
                        raw_json.get("toolCalls") or raw_json.get("toolCall") or []
                    )
                    if isinstance(tool_calls, dict):
                        tool_calls = [tool_calls]

                    # Extract file paths from tool call parameters
                    file_paths_to_check = [tool_desc] if tool_desc else []
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            params = tc.get("parameters") or tc.get("arguments") or {}
                            if isinstance(params, dict):
                                path = params.get("path", "") or params.get("file", "")
                                if path:
                                    file_paths_to_check.append(path)

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
                                    processed_messages.append(
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
                                        }
                                    )
                                    # Remove from map to avoid duplicate indicators
                                    del plans_by_file_path[plan_file_path]
                                    break

                tool_call_group = []

            # Check if this is a thinking message
            if msg_type == "thinking":
                msg["is_thinking"] = True

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

        # Insert plan content right after the final tool call group if we have one
        if pending_plan_content:
            processed_messages.append(
                {
                    "type": "plan_content",
                    "plan": pending_plan_content,
                }
            )
            pending_plan_content = None

        # Insert terminal commands right after the final tool call group
        if pending_terminal_commands:
            logger.debug(
                f"get_chat: inserting {len(pending_terminal_commands)} terminal command(s) "
                f"after final tool call group"
            )
        for terminal_cmd in pending_terminal_commands:
            processed_messages.append(
                {
                    "type": "terminal_command",
                    "terminal_command": terminal_cmd,
                }
            )
        pending_terminal_commands = []

        # Check if this final tool call group created any plans
        for tool_msg in tool_call_group:
            # Check tool_description (from classification)
            tool_desc = tool_msg.get("tool_description", "")
            # Also check raw_json for actual file path in parameters
            raw_json = tool_msg.get("raw_json", {})
            tool_calls = raw_json.get("toolCalls") or raw_json.get("toolCall") or []
            if isinstance(tool_calls, dict):
                tool_calls = [tool_calls]

            # Extract file paths from tool call parameters
            file_paths_to_check = [tool_desc] if tool_desc else []
            for tc in tool_calls:
                if isinstance(tc, dict):
                    params = tc.get("parameters") or tc.get("arguments") or {}
                    if isinstance(params, dict):
                        path = params.get("path", "") or params.get("file", "")
                        if path:
                            file_paths_to_check.append(path)

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
                            processed_messages.append(
                                {
                                    "type": "plan_created",
                                    "plan": {
                                        "id": plan_info["id"],
                                        "plan_id": plan_info["plan_id"],
                                        "name": plan_info["name"],
                                        "file_path": plan_info.get("file_path"),
                                        "created_at": plan_info.get("created_at"),
                                    },
                                }
                            )
                            del plans_by_file_path[plan_file_path]
                            break

    # If any plans weren't matched to tool calls, add indicators after first message as fallback
    if plans_by_file_path and processed_messages:
        for plan_info in plans_by_file_path.values():
            # Insert after first message
            processed_messages.insert(
                1,
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
            )

    chat["processed_messages"] = processed_messages

    # Log summary of processed messages
    terminal_count = sum(1 for m in processed_messages if m.get("type") == "terminal_command")
    tool_group_count = sum(1 for m in processed_messages if m.get("type") == "tool_call_group")
    logger.debug(
        f"get_chat: processed {len(processed_messages)} messages total: "
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

    # Check if API key is configured
    import os

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY environment variable not set. "
            "Set it to use chat summarization.",
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

    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Summarization service not available: {str(e)}",
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error("Error generating summary: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate summary: {str(e)}",
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
