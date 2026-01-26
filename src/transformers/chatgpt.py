"""
ChatGPT transformer for converting raw ChatGPT data to domain models.

Transforms raw ChatGPT conversation data (from ChatGPT API exports) into
normalized Chat domain models for storage in the domain database.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.core.db import ChatDatabase
from src.core.db.raw_storage import RawStorage
from src.core.models import Chat, ChatMode, Message, MessageRole, MessageType
from src.transformers.base import BaseTransformer

logger = logging.getLogger(__name__)


class ChatGPTTransformer(BaseTransformer):
    """
    Transformer for ChatGPT conversation data.

    Converts raw ChatGPT conversation dictionaries (from API exports) into
    normalized Chat domain models. Handles both Unix epoch and ISO timestamp
    formats used by ChatGPT.

    Attributes
    ----------
    source_name : str
        Source identifier: 'chatgpt'
    raw_storage : RawStorage
        Storage containing raw extracted data
    domain_db : ChatDatabase
        Domain database for transformed data
    """

    def __init__(self, raw_storage: RawStorage, domain_db: ChatDatabase):
        """
        Initialize ChatGPT transformer.

        Parameters
        ----------
        raw_storage : RawStorage
            Storage containing raw extracted data
        domain_db : ChatDatabase
            Domain database for storing transformed data
        """
        super().__init__(raw_storage, domain_db)

    @property
    def source_name(self) -> str:
        """
        Source identifier matching the extractor.

        Returns
        -------
        str
            Source name: 'chatgpt'
        """
        return "chatgpt"

    def _parse_chatgpt_timestamp(self, timestamp: Optional[Any]) -> Optional[datetime]:
        """
        Parse ChatGPT timestamp (supports both Unix epoch and ISO strings).

        ChatGPT API returns timestamps in two formats:
        - Unix epoch: 1766681665.991872 (float)
        - ISO string: "2025-12-30T22:12:41.767145Z"

        Parameters
        ----
        timestamp : float, str, or None
            Timestamp value from ChatGPT API

        Returns
        ----
        datetime or None
            Parsed datetime or None if parsing fails
        """
        if timestamp is None:
            return None

        try:
            if isinstance(timestamp, (int, float)):
                # Unix epoch timestamp
                return datetime.fromtimestamp(float(timestamp))
            elif isinstance(timestamp, str):
                # ISO format string
                if timestamp.endswith("Z"):
                    timestamp = timestamp[:-1] + "+00:00"
                return datetime.fromisoformat(timestamp)
        except (ValueError, TypeError, OSError) as e:
            logger.debug("Could not parse ChatGPT timestamp %s: %s", timestamp, e)

        return None

    def transform(self, raw_data: Dict[str, Any]) -> Optional[Chat]:
        """
        Transform raw ChatGPT conversation data to Chat domain model.

        The raw_data is the full conversation dict containing:
        - id: conversation ID
        - title: conversation title
        - create_time: creation timestamp (Unix epoch or ISO string)
        - update_time: last update timestamp (Unix epoch or ISO string)
        - chat_messages: list of message dicts (already flattened by ChatGPTReader)

        Key differences from other sources:
        - Uses "id" instead of "uuid"
        - Timestamps can be Unix epoch or ISO strings
        - Messages already flattened by ChatGPTReader
        - Sender is "user"/"assistant" vs "human"/"assistant"

        Parameters
        ----
        raw_data : Dict[str, Any]
            Raw conversation from ChatGPT API (includes chat_messages from reader)

        Returns
        ----
        Chat or None
            Chat domain model, or None if transformation fails
        """
        conv_id = raw_data.get("id")
        if not conv_id:
            return None

        # Extract title
        title = raw_data.get("title", "Untitled Chat")

        # Extract timestamps (ChatGPT uses both Unix epoch and ISO strings)
        created_at = None
        create_time = raw_data.get("create_time")
        if create_time:
            created_at = self._parse_chatgpt_timestamp(create_time)

        last_updated_at = None
        update_time = raw_data.get("update_time")
        if update_time:
            last_updated_at = self._parse_chatgpt_timestamp(update_time)

        # Extract messages (already flattened by ChatGPTReader)
        messages = []
        chat_messages = raw_data.get("chat_messages", [])

        for msg_data in chat_messages:
            # Map sender to role
            sender = msg_data.get("sender", "")
            if sender == "user":
                role = MessageRole.USER
            elif sender == "assistant":
                role = MessageRole.ASSISTANT
            else:
                # Skip system messages and unknown types
                continue

            # Extract text from content array
            text_parts = []
            content_items = msg_data.get("content", [])
            for item in content_items:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)

            text = "\n".join(text_parts) if text_parts else ""

            # Extract timestamp
            msg_created_at = None
            if msg_data.get("created_at"):
                msg_created_at = self._parse_chatgpt_timestamp(msg_data["created_at"])

            # Classify message type
            message_type = MessageType.RESPONSE if text else MessageType.EMPTY

            message = Message(
                role=role,
                text=text,
                rich_text="",  # ChatGPT doesn't expose rich text separately
                created_at=msg_created_at or created_at,
                cursor_bubble_id=msg_data.get("uuid"),  # Message UUID if available
                raw_json=msg_data,
                message_type=message_type,
            )
            messages.append(message)

        # ChatGPT conversations are always chat mode
        mode = ChatMode.CHAT

        # Create chat
        chat = Chat(
            cursor_composer_id=conv_id,  # Reuse this field for ChatGPT conversation ID
            workspace_id=None,  # ChatGPT conversations don't have workspaces
            title=title,
            mode=mode,
            created_at=created_at,
            last_updated_at=last_updated_at,
            source="chatgpt",  # Important: mark as chatgpt source!
            messages=messages,
            relevant_files=[],  # ChatGPT API doesn't expose relevant files in this format
        )

        return chat
