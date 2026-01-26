"""
Claude Code transformer for converting raw Claude Code session data to Chat models.

Part of the ELT (Extract-Load-Transform) architecture.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.core.models import Chat, ChatMode, Message, MessageRole, MessageType
from src.transformers.base import BaseTransformer

logger = logging.getLogger(__name__)


class ClaudeCodeTransformer(BaseTransformer):
    """
    Transformer for Claude Code session data.

    Converts raw Claude Code session dictionaries (from ClaudeCodeReader) into
    normalized Chat domain models for storage in the domain database.

    Attributes
    ----------
    source_name : str
        Returns 'claude-code' to match ClaudeCodeExtractor
    """

    @property
    def source_name(self) -> str:
        """
        Source identifier matching the extractor.

        Returns
        -------
        str
            Source name: 'claude-code'
        """
        return "claude-code"

    def transform(self, raw_data: Dict[str, Any]) -> Optional[Chat]:
        """
        Transform raw Claude Code session data to Chat domain model.

        Parameters
        ----------
        raw_data : Dict[str, Any]
            Raw session data from ClaudeCodeReader (the full session dict with
            session_id, summary, messages, metadata, etc.)

        Returns
        -------
        Chat or None
            Transformed Chat model, or None if transformation fails
        """
        session_id = raw_data.get("session_id")
        if not session_id:
            logger.warning("Session data missing session_id, skipping")
            return None

        # Extract title from summary or metadata
        title = raw_data.get("summary") or "Untitled Session"
        if title == "Untitled Session":
            # Try to extract from metadata slug
            metadata = raw_data.get("metadata", {})
            slug = metadata.get("slug")
            if slug:
                title = slug.replace("-", " ").title()

        # Extract messages
        raw_messages = raw_data.get("messages", [])
        messages = []
        model_used = None
        total_input_tokens = 0
        total_output_tokens = 0

        for msg_data in raw_messages:
            # Map role
            role_str = msg_data.get("role", "user")
            if role_str == "user":
                role = MessageRole.USER
            elif role_str == "assistant":
                role = MessageRole.ASSISTANT
            else:
                continue

            # Extract text content
            text = msg_data.get("content", "")

            # Extract thinking content if present
            thinking = msg_data.get("thinking")
            if thinking:
                text = (
                    f"[Thinking]\n{thinking}\n\n{text}" if text else f"[Thinking]\n{thinking}"
                )

            # Extract tool calls if present
            tool_calls = msg_data.get("tool_calls")
            if tool_calls:
                tool_summary = []
                for tc in tool_calls:
                    tool_name = tc.get("name", "unknown")
                    tool_summary.append(f"[Tool: {tool_name}]")
                if tool_summary:
                    tool_text = "\n".join(tool_summary)
                    text = f"{text}\n\n{tool_text}" if text else tool_text

            # Parse timestamp
            msg_created_at = None
            timestamp_str = msg_data.get("timestamp")
            if timestamp_str:
                try:
                    if timestamp_str.endswith("Z"):
                        timestamp_str = timestamp_str[:-1] + "+00:00"
                    msg_created_at = datetime.fromisoformat(timestamp_str)
                except (ValueError, TypeError):
                    pass

            # Classify message type
            if msg_data.get("thinking"):
                message_type = MessageType.THINKING
            elif msg_data.get("tool_calls"):
                message_type = MessageType.TOOL_CALL
            elif text:
                message_type = MessageType.RESPONSE
            else:
                message_type = MessageType.EMPTY

            # Extract model and usage from assistant messages
            if role == MessageRole.ASSISTANT:
                if not model_used:
                    model_used = msg_data.get("model")
                usage = msg_data.get("usage", {})
                if usage:
                    total_input_tokens += usage.get("input_tokens", 0)
                    total_output_tokens += usage.get("output_tokens", 0)

            message = Message(
                role=role,
                text=text,
                rich_text="",
                created_at=msg_created_at,
                cursor_bubble_id=msg_data.get("uuid"),
                raw_json=msg_data,
                message_type=message_type,
            )
            messages.append(message)

        # Skip empty sessions
        if not messages:
            logger.debug("Session %s has no messages, skipping", session_id)
            return None

        # Extract timestamps from first/last messages
        created_at = messages[0].created_at if messages else None
        last_updated_at = messages[-1].created_at if messages else None

        # Determine mode based on tool usage
        has_tool_calls = any(m.message_type == MessageType.TOOL_CALL for m in messages)
        mode = ChatMode.AGENT if has_tool_calls else ChatMode.CHAT

        # Calculate estimated cost (rough estimate based on Claude pricing)
        estimated_cost = None
        if total_input_tokens or total_output_tokens:
            # Use approximate pricing (varies by model)
            # Sonnet: $3/1M input, $15/1M output
            # Opus: $15/1M input, $75/1M output
            if model_used and "opus" in model_used.lower():
                estimated_cost = (total_input_tokens * 15 + total_output_tokens * 75) / 1_000_000
            else:
                estimated_cost = (total_input_tokens * 3 + total_output_tokens * 15) / 1_000_000

        # Create chat
        chat = Chat(
            cursor_composer_id=session_id,
            workspace_id=None,  # Could be inferred from project_path later
            title=title,
            mode=mode,
            created_at=created_at,
            last_updated_at=last_updated_at,
            source="claude-code",
            summary=raw_data.get("summary"),
            model=model_used,
            estimated_cost=estimated_cost,
            messages=messages,
            relevant_files=[],  # Could extract from tool calls later
        )

        return chat
