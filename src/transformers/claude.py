"""
Claude.ai transformer for converting raw Claude.ai conversation data to Chat models.

Transforms Claude.ai conversation exports (from RawStorage) into normalized
Chat domain models for storage in the domain database.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.core.models import Chat, ChatMode, Message, MessageRole, MessageType
from src.transformers.base import BaseTransformer

logger = logging.getLogger(__name__)


class ClaudeTransformer(BaseTransformer):
    """
    Transformer for Claude.ai conversation data.

    Converts raw Claude.ai conversation dictionaries (from RawStorage) into
    normalized Chat domain models.

    The raw_data from RawStorage is the full conversation dict containing:
    - uuid: conversation identifier
    - name/summary: conversation title
    - created_at/updated_at: ISO timestamps
    - chat_messages: array of message objects
    - model: AI model identifier
    """

    @property
    def source_name(self) -> str:
        """
        Source identifier for Claude.ai conversations.

        Returns
        -------
        str
            'claude.ai'
        """
        return "claude.ai"

    def transform(self, raw_data: Dict[str, Any]) -> Optional[Chat]:
        """
        Transform raw Claude.ai conversation data to Chat domain model.

        Parameters
        ----------
        raw_data : Dict[str, Any]
            Raw conversation data from RawStorage (full conversation dict)

        Returns
        -------
        Chat or None
            Transformed Chat model, or None if transformation fails
        """
        conv_id = raw_data.get("uuid")
        if not conv_id:
            logger.debug("Skipping Claude conversation without uuid")
            return None

        # Extract title
        title = (
            raw_data.get("name")
            or raw_data.get("summary")
            or "Untitled Chat"
        )

        # Extract timestamps with 'Z' suffix handling
        created_at = self._parse_timestamp(raw_data.get("created_at"))
        last_updated_at = self._parse_timestamp(raw_data.get("updated_at"))

        # Extract messages
        messages = []
        chat_messages = raw_data.get("chat_messages", [])

        for msg_data in chat_messages:
            # Map sender to role
            sender = msg_data.get("sender", "")
            if sender == "human":
                role = MessageRole.USER
            elif sender == "assistant":
                role = MessageRole.ASSISTANT
            else:
                # Skip unknown sender types
                logger.debug("Skipping message with unknown sender: %s", sender)
                continue

            # Extract text from content blocks array
            text = self._extract_text_from_content(msg_data.get("content", []))
            
            # Fallback: check for text field directly on message
            if not text:
                text = msg_data.get("text", "")

            # Extract message timestamp
            msg_created_at = self._parse_timestamp(msg_data.get("created_at"))
            
            # Use conversation created_at as fallback for message timestamp
            if not msg_created_at:
                msg_created_at = created_at

            # Classify message type
            message_type = MessageType.RESPONSE if text else MessageType.EMPTY

            message = Message(
                role=role,
                text=text,
                rich_text="",  # Claude.ai doesn't provide rich_text in this format
                created_at=msg_created_at,
                cursor_bubble_id=msg_data.get("uuid"),
                raw_json=msg_data,
                message_type=message_type,
            )
            messages.append(message)

        # Extract model
        model = raw_data.get("model")
        mode = ChatMode.CHAT  # Claude conversations are always chat mode

        # Create chat
        chat = Chat(
            cursor_composer_id=conv_id,  # Reuse this field for Claude conversation ID
            workspace_id=None,  # Claude conversations don't have workspaces
            title=title,
            mode=mode,
            created_at=created_at,
            last_updated_at=last_updated_at,
            source="claude.ai",
            model=model,
            messages=messages,
            relevant_files=[],  # Claude API doesn't expose relevant files
        )

        return chat

    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """
        Parse ISO timestamp string with 'Z' suffix handling.

        Parameters
        ----------
        timestamp_str : str, optional
            ISO format timestamp string (may end with 'Z')

        Returns
        -------
        datetime, optional
            Parsed datetime or None if parsing fails
        """
        if not timestamp_str:
            return None
        try:
            # Handle 'Z' suffix (UTC indicator)
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            return datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError) as e:
            logger.debug("Could not parse timestamp '%s': %s", timestamp_str, e)
            return None

    def _extract_text_from_content(self, content: list) -> str:
        """
        Extract text from Claude.ai content blocks array.

        Claude stores content as an array of content blocks, where each block
        has a 'type' field. We extract all 'text' type blocks and join them.

        Parameters
        ----------
        content : list
            Array of content blocks

        Returns
        -------
        str
            Extracted text content, joined with double newlines
        """
        text_parts = []
        for content_block in content:
            if content_block.get("type") == "text":
                block_text = content_block.get("text", "")
                if block_text:
                    text_parts.append(block_text)
        
        return "\n\n".join(text_parts) if text_parts else ""
