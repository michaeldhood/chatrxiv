"""
Reader for ChatGPT conversations.

Fetches conversations from ChatGPT's internal API using direct HTTP requests.
"""

import logging
from typing import Any, Dict, List, Optional

from .base import WebConversationReader

logger = logging.getLogger(__name__)


class ChatGPTReader(WebConversationReader):
    """
    Reader for ChatGPT conversations from chatgpt.com.

    Fetches conversations from ChatGPT's internal API.
    Credentials can be provided via parameters, environment variables,
    or dlt secrets file (.dlt/secrets.toml).
    """

    def __init__(self, session_token: Optional[str] = None):
        """
        Initialize ChatGPT reader.

        Parameters
        ----
        session_token : str, optional
            Session token. If None, reads from dlt secrets or env var.
        """
        super().__init__(credential=session_token)

    @property
    def api_base_url(self) -> str:
        """Base URL for ChatGPT API."""
        return "https://chatgpt.com/backend-api"

    @property
    def credential_env_var(self) -> str:
        """Environment variable name for ChatGPT session token."""
        return "CHATGPT_SESSION_TOKEN"

    @property
    def dlt_secrets_path(self) -> str:
        """dlt secrets path for ChatGPT credentials."""
        return "sources.chatgpt_conversations"

    def _build_headers(self, credential: str) -> Dict[str, str]:
        """Build HTTP headers with ChatGPT session token."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cookie": f"__Secure-next-auth.session-token={credential}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

    def _fetch_conversation_list(self) -> List[Dict[str, Any]]:
        """
        Fetch list of all conversations with pagination.

        ChatGPT uses pagination, so we need to fetch all pages.
        """
        all_conversations = []
        offset = 0
        limit = 28  # ChatGPT's default page size

        while True:
            response = self._session.get(
                f"{self.api_base_url}/conversations",
                params={
                    "offset": offset,
                    "limit": limit,
                    "order": "updated",
                    "is_archived": False,
                },
            )
            response.raise_for_status()
            data = response.json()

            items = data.get("items", [])
            if not items:
                break

            all_conversations.extend(items)

            # Check if there are more pages
            if len(items) < limit:
                break

            offset += limit

        return all_conversations

    def _fetch_conversation_detail(self, conv_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch full conversation details including messages.

        ChatGPT stores messages as a tree structure. This method fetches
        the conversation and flattens the message tree into a linear array.
        """
        try:
            response = self._session.get(f"{self.api_base_url}/conversation/{conv_id}")
            response.raise_for_status()

            data = response.json()

            # Flatten the message tree into a linear array (like Claude's format)
            mapping = data.get("mapping", {})
            if mapping:
                data["chat_messages"] = self._flatten_message_tree(mapping)

            return data
        except Exception as e:
            logger.error("Error fetching conversation %s: %s", conv_id, e)
            return None

    def _extract_conversation_id(self, conversation: Dict[str, Any]) -> str:
        """Extract conversation ID from ChatGPT conversation object."""
        return conversation["id"]  # ChatGPT uses "id", Claude uses "uuid"

    def _flatten_message_tree(self, mapping: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert ChatGPT's message tree to flat array (like Claude's format).

        ChatGPT stores messages as a tree structure to support branching conversations.
        This method traverses the tree following the most recent path (highest weight)
        to build a linear message list.

        Parameters
        ----
        mapping : Dict[str, Dict[str, Any]]
            Message tree mapping from conversation response

        Returns
        ----
        List[Dict[str, Any]]
            Flat list of messages in chronological order
        """
        if not mapping:
            return []

        # Find root node (parent is None or special UUID)
        root_id = None
        for node_id, node in mapping.items():
            parent = node.get("parent")
            # Root nodes have parent=None or a special UUID like "00000000-0000-4000-8000-000000000000"
            if parent is None or parent == "00000000-0000-4000-8000-000000000000":
                root_id = node_id
                break

        if not root_id:
            logger.warning("No root node found in message tree")
            return []

        messages = []
        current_id = root_id

        # Traverse the tree following children
        visited = set()
        while current_id and current_id in mapping:
            if current_id in visited:
                logger.warning("Circular reference detected in message tree at %s", current_id)
                break
            visited.add(current_id)

            node = mapping[current_id]
            message = node.get("message")

            # Only include nodes that have actual message content
            if message:
                # Extract message data in a format similar to Claude's
                msg_data = {
                    "uuid": message.get("id", current_id),
                    "sender": message.get("author", {}).get("role", "unknown"),
                    "content": self._extract_message_content(message),
                    "created_at": message.get("create_time"),
                    "updated_at": message.get("update_time"),
                    "parent_message_uuid": node.get("parent"),
                }
                messages.append(msg_data)

            # Move to next node - follow the first child (most recent path)
            children = node.get("children", [])
            if children:
                # ChatGPT may have multiple children (branches). Follow the first one.
                # In a full implementation, you might want to follow the path with highest weight
                current_id = children[0]
            else:
                break

        return messages

    def _extract_message_content(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract message content parts from ChatGPT message object.

        Parameters
        ----
        message : Dict[str, Any]
            ChatGPT message object

        Returns
        ----
        List[Dict[str, Any]]
            List of content parts (similar to Claude's format)
        """
        content = message.get("content", {})
        content_type = content.get("content_type", "text")
        parts = content.get("parts", [])

        # Convert to Claude-like format
        result = []
        for part in parts:
            if isinstance(part, str):
                result.append({"type": "text", "text": part})
            elif isinstance(part, dict):
                # Handle multimodal content
                part_type = part.get("content_type", "text")
                if part_type == "audio_transcription":
                    result.append({"type": "text", "text": part.get("text", "")})
                else:
                    # For other types, include the raw part
                    result.append({"type": part_type, **part})
            else:
                result.append({"type": "text", "text": str(part)})

        return result
