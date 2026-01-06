"""
Reader for ChatGPT conversations.

Fetches conversations from ChatGPT's internal API using direct HTTP requests.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .base import WebConversationReader

logger = logging.getLogger(__name__)

# #region agent log
import os
def _debug_log(hypothesis_id: str, location: str, message: str, data: dict = None):
    import time
    # Use project root relative path instead of hardcoded absolute path
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    debug_log_path = os.path.join(project_root, ".cursor", "debug.log")
    entry = {"hypothesisId": hypothesis_id, "location": location, "message": message, "data": data or {}, "timestamp": int(time.time() * 1000), "sessionId": "debug-session"}
    os.makedirs(os.path.dirname(debug_log_path), exist_ok=True)
    with open(debug_log_path, "a") as f: f.write(json.dumps(entry) + "\n")
# #endregion


class ChatGPTReader(WebConversationReader):
    """
    Reader for ChatGPT conversations from chatgpt.com.

    Fetches conversations from ChatGPT's internal API.
    Credentials can be provided via parameters, environment variables,
    or dlt secrets file (.dlt/secrets.toml).
    """

    def __init__(
        self,
        session_token: Optional[str] = None,
        csrf_token: Optional[str] = None,
        cf_clearance: Optional[str] = None,
        oai_did: Optional[str] = None,
        puid: Optional[str] = None,
    ):
        """
        Initialize ChatGPT reader.

        Parameters
        ----
        session_token : str, optional
            Session token. If None, reads from dlt secrets or env var.
        csrf_token : str, optional
            CSRF token from __Host-next-auth.csrf-token cookie.
        cf_clearance : str, optional
            Cloudflare clearance token.
        oai_did : str, optional
            OpenAI device ID.
        puid : str, optional
            User ID cookie.
        """
        # Load additional cookies from dlt secrets if not provided
        import dlt
        try:
            secrets = dlt.secrets.get("sources.chatgpt_conversations", {})
            self._csrf_token = csrf_token or secrets.get("csrf_token")
            self._cf_clearance = cf_clearance or secrets.get("cf_clearance")
            self._oai_did = oai_did or secrets.get("oai_did")
            self._puid = puid or secrets.get("puid")
            # #region agent log
            _debug_log("H0", "chatgpt_reader.py:__init__", "Loaded secrets", {
                "has_session_cookie": "session_cookie" in secrets,
                "has_csrf_token": "csrf_token" in secrets,
                "has_cf_clearance": "cf_clearance" in secrets,
                "has_oai_did": "oai_did" in secrets,
                "has_puid": "puid" in secrets,
            })
            # #endregion
        except Exception as e:
            # #region agent log
            _debug_log("H0", "chatgpt_reader.py:__init__", "Failed to load secrets", {"error": str(e)})
            # #endregion
            self._csrf_token = csrf_token
            self._cf_clearance = cf_clearance
            self._oai_did = oai_did
            self._puid = puid
        
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
        """Build HTTP headers with ChatGPT session token and additional cookies."""
        # #region agent log
        _debug_log("H0", "chatgpt_reader.py:_build_headers", "Building headers", {
            "session_token_len": len(credential) if credential else 0,
            "has_csrf": bool(self._csrf_token),
            "has_cf_clearance": bool(self._cf_clearance),
            "has_oai_did": bool(self._oai_did),
            "has_puid": bool(self._puid),
        })
        # #endregion
        
        # Build cookie string with all available cookies
        cookies = [f"__Secure-next-auth.session-token={credential}"]
        
        # H1: Add CSRF token if available
        if self._csrf_token:
            cookies.append(f"__Host-next-auth.csrf-token={self._csrf_token}")
            # #region agent log
            _debug_log("H1", "chatgpt_reader.py:_build_headers", "Added CSRF token", {"csrf_len": len(self._csrf_token)})
            # #endregion
        
        # H3: Add Cloudflare clearance if available
        if self._cf_clearance:
            cookies.append(f"cf_clearance={self._cf_clearance}")
            # #region agent log
            _debug_log("H3", "chatgpt_reader.py:_build_headers", "Added cf_clearance", {"cf_len": len(self._cf_clearance)})
            # #endregion
        
        # H4: Add device ID if available
        if self._oai_did:
            cookies.append(f"oai-did={self._oai_did}")
            # #region agent log
            _debug_log("H4", "chatgpt_reader.py:_build_headers", "Added oai-did", {"oai_did": self._oai_did[:10] + "..." if len(self._oai_did) > 10 else self._oai_did})
            # #endregion
        
        # H4: Add user ID if available
        if self._puid:
            cookies.append(f"_puid={self._puid}")
            # #region agent log
            _debug_log("H4", "chatgpt_reader.py:_build_headers", "Added _puid", {"puid": self._puid[:10] + "..." if len(self._puid) > 10 else self._puid})
            # #endregion
        
        cookie_str = "; ".join(cookies)
        
        # #region agent log
        _debug_log("H0", "chatgpt_reader.py:_build_headers", "Final cookie count", {"num_cookies": len(cookies), "cookie_names": [c.split("=")[0] for c in cookies]})
        # #endregion
        
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cookie": cookie_str,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://chatgpt.com/",
            "Origin": "https://chatgpt.com",
        }

    def _fetch_conversation_list(self) -> List[Dict[str, Any]]:
        """
        Fetch list of all conversations with pagination.

        ChatGPT uses pagination, so we need to fetch all pages.
        Fetches both regular and archived conversations.
        """
        all_conversations = []
        limit = 28  # ChatGPT's default page size

        # #region agent log
        _debug_log("H0", "chatgpt_reader.py:_fetch_conversation_list", "Starting fetch", {"api_url": self.api_base_url})
        # #endregion

        # Fetch both non-archived and archived conversations
        for is_archived in [False, True]:
            offset = 0
            # #region agent log
            _debug_log("H0", "chatgpt_reader.py:_fetch_conversation_list", f"Fetching conversations", {"is_archived": is_archived})
            # #endregion
            
            while True:
                response = self._session.get(
                    f"{self.api_base_url}/conversations",
                    params={
                        "offset": offset,
                        "limit": limit,
                        "order": "updated",
                        "is_archived": is_archived,
                    },
                )
                
                # #region agent log
                _debug_log("H0", "chatgpt_reader.py:_fetch_conversation_list", "API response received", {
                    "status_code": response.status_code,
                    "response_text_preview": response.text[:500] if response.text else None,
                })
                # #endregion
                
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

        # #region agent log
        _debug_log("H0", "chatgpt_reader.py:_fetch_conversation_list", "Fetch complete", {"total_conversations": len(all_conversations)})
        # #endregion
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
                data["chat_messages"] = ChatGPTReader._flatten_message_tree(mapping)

            return data
        except Exception as e:
            logger.error("Error fetching conversation %s: %s", conv_id, e)
            return None

    def _extract_conversation_id(self, conversation: Dict[str, Any]) -> str:
        """Extract conversation ID from ChatGPT conversation object."""
        return conversation["id"]  # ChatGPT uses "id", Claude uses "uuid"

    @staticmethod
    def _flatten_message_tree(mapping: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
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
                    "content": ChatGPTReader._extract_message_content(message),
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

    @staticmethod
    def _extract_message_content(message: Dict[str, Any]) -> List[Dict[str, Any]]:
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
