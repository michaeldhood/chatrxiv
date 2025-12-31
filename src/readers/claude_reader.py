"""
Reader for Claude.ai conversations.

Fetches conversations from Claude.ai's internal API using direct HTTP requests.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import dlt  # Only used for reading secrets

from .base import WebConversationReader

logger = logging.getLogger(__name__)


class ClaudeReader(WebConversationReader):
    """
    Reader for Claude.ai conversations.

    Fetches conversations from Claude.ai's internal API.
    Credentials can be provided via parameters, environment variables,
    or dlt secrets file (.dlt/secrets.toml).
    """

    def __init__(
        self,
        org_id: Optional[str] = None,
        session_cookie: Optional[str] = None,
    ):
        """
        Initialize Claude reader.

        Parameters
        ----
        org_id : str, optional
            Organization ID. If None, reads from dlt secrets or env var.
        session_cookie : str, optional
            Session cookie. If None, reads from dlt secrets or env var.
        """
        self.org_id = self._resolve_org_id(org_id)
        super().__init__(credential=session_cookie)

    @property
    def api_base_url(self) -> str:
        """Base URL for Claude.ai API."""
        return f"https://claude.ai/api/organizations/{self.org_id}"

    @property
    def credential_env_var(self) -> str:
        """Environment variable name for Claude session cookie."""
        return "CLAUDE_SESSION_COOKIE"

    @property
    def dlt_secrets_path(self) -> str:
        """dlt secrets path for Claude credentials."""
        return "sources.claude_conversations"

    def _build_headers(self, credential: str) -> Dict[str, str]:
        """Build HTTP headers with Claude session cookie."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cookie": f"sessionKey={credential}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

    def _fetch_conversation_list(self) -> List[Dict[str, Any]]:
        """Fetch list of all conversations from Claude.ai API."""
        url = f"{self.api_base_url}/chat_conversations"

        response = self._session.get(url)
        response.raise_for_status()

        conversations = response.json()
        if not isinstance(conversations, list):
            logger.warning("Unexpected response format from Claude API")
            return []

        return conversations

    def _fetch_conversation_detail(self, conv_id: str) -> Optional[Dict[str, Any]]:
        """Fetch full conversation details including messages."""
        url = f"{self.api_base_url}/chat_conversations/{conv_id}"
        params = {
            "tree": "True",
            "rendering_mode": "messages",
            "render_all_tools": "true",
        }

        try:
            response = self._session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("Error fetching conversation %s: %s", conv_id, e)
            return None

    def _extract_conversation_id(self, conversation: Dict[str, Any]) -> str:
        """Extract conversation UUID from Claude conversation object."""
        return conversation["uuid"]

    def _resolve_org_id(self, param_value: Optional[str]) -> str:
        """
        Resolve organization ID from parameter, environment variable, or dlt secrets.

        Parameters
        ----
        param_value : Optional[str]
            Organization ID passed to constructor

        Returns
        ----
        str
            Resolved organization ID

        Raises
        ---
        ValueError
            If org_id cannot be resolved from any source
        """
        if param_value:
            return param_value

        env_value = os.getenv("CLAUDE_ORG_ID")
        if env_value:
            return env_value

        try:
            secrets = dlt.secrets.get("sources.claude_conversations", {})
            dlt_value = secrets.get("org_id")
            if dlt_value:
                return dlt_value
        except Exception:
            pass  # dlt secrets not available or misconfigured

        raise ValueError(
            "org_id must be provided via parameter, CLAUDE_ORG_ID env var, "
            "or dlt secrets"
        )
