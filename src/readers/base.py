"""
Base class for web-based AI conversation readers.

Provides common functionality for fetching conversations from web APIs
that require session-based authentication.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional

import dlt  # Only used for reading secrets
import requests

logger = logging.getLogger(__name__)


class WebConversationReader(ABC):
    """
    Base class for web-based AI conversation readers.

    Handles common patterns:
    - Credential resolution (param → env var → dlt secrets)
    - HTTP session management
    - Error handling
    - Iterator pattern for bulk reads

    Subclasses must implement platform-specific methods for:
    - API endpoints
    - Authentication headers
    - Response parsing
    """

    def __init__(self, credential: Optional[str] = None):
        """
        Initialize reader with credential resolution.

        Parameters
        ----
        credential : str, optional
            Session credential (cookie/token). If None, resolves from env or dlt secrets.

        Raises
        ---
        ValueError
            If credential cannot be resolved from any source.
        """
        self.credential = self._resolve_credential(credential)
        self._session = requests.Session()
        self._session.headers.update(self._build_headers(self.credential))

    @property
    @abstractmethod
    def api_base_url(self) -> str:
        """
        Base URL for the API.

        Returns
        ----
        str
            Base URL (e.g., 'https://claude.ai/api/organizations/{org_id}')
        """

    @property
    @abstractmethod
    def credential_env_var(self) -> str:
        """
        Environment variable name for credentials.

        Returns
        ----
        str
            Env var name (e.g., 'CLAUDE_SESSION_COOKIE')
        """

    @property
    @abstractmethod
    def dlt_secrets_path(self) -> str:
        """
        dlt secrets configuration path.

        Returns
        ----
        str
            Secrets path (e.g., 'sources.claude_conversations')
        """

    @abstractmethod
    def _build_headers(self, credential: str) -> Dict[str, str]:
        """
        Build HTTP headers with authentication.

        Parameters
        ----
        credential : str
            Session credential value

        Returns
        ----
        Dict[str, str]
            HTTP headers dictionary with Cookie header set appropriately
        """

    @abstractmethod
    def _fetch_conversation_list(self) -> List[Dict[str, Any]]:
        """
        Fetch list of all conversations from the API.

        Returns
        ----
        List[Dict[str, Any]]
            List of conversation metadata objects
        """

    @abstractmethod
    def _fetch_conversation_detail(self, conv_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch full conversation details including messages.

        Parameters
        ----
        conv_id : str
            Conversation identifier

        Returns
        ----
        Optional[Dict[str, Any]]
            Full conversation object, or None if not found
        """

    @abstractmethod
    def _extract_conversation_id(self, conversation: Dict[str, Any]) -> str:
        """
        Extract conversation ID from metadata object.

        Parameters
        ----
        conversation : Dict[str, Any]
            Conversation metadata object

        Returns
        ----
        str
            Conversation identifier (field name varies by platform)
        """

    def _resolve_credential(self, param_value: Optional[str]) -> str:
        """
        Resolve credential from parameter, environment variable, or dlt secrets.

        Resolution order:
        1. Constructor parameter
        2. Environment variable
        3. dlt secrets file

        Parameters
        ----
        param_value : Optional[str]
            Value passed to constructor

        Returns
        ----
        str
            Resolved credential value

        Raises
        ---
        ValueError
            If credential cannot be resolved from any source
        """
        if param_value:
            return param_value

        env_value = os.getenv(self.credential_env_var)
        if env_value:
            return env_value

        try:
            secrets = dlt.secrets.get(self.dlt_secrets_path, {})
            # Try common field names
            dlt_value = (
                secrets.get("credential")
                or secrets.get("session_cookie")
                or secrets.get("session_token")
            )
            if dlt_value:
                return dlt_value
        except Exception:
            pass  # dlt secrets not available or misconfigured

        raise ValueError(
            f"Credential must be provided via parameter, {self.credential_env_var} env var, "
            f"or dlt secrets at {self.dlt_secrets_path}"
        )

    def get_conversation_list(self) -> List[Dict[str, Any]]:
        """
        Fetch conversation metadata only (no details).

        Returns
        ----
        List[Dict[str, Any]]
            List of conversation objects with id, title, timestamps, etc.
        """
        return self._fetch_conversation_list()

    def read_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Read a specific conversation by ID.

        Parameters
        ----
        conversation_id : str
            Conversation identifier

        Returns
        ----
        Optional[Dict[str, Any]]
            Full conversation object with messages, or None if not found
        """
        return self._fetch_conversation_detail(conversation_id)

    def read_all_conversations(self) -> Iterator[Dict[str, Any]]:
        """
        Read all conversations with full details.

        Fetches the conversation list, then fetches full details for each.
        Yields full conversation objects one at a time.

        Yields
        ----
        Dict[str, Any]
            Full conversation objects with messages
        """
        logger.info("Fetching conversation list...")

        try:
            conversations = self._fetch_conversation_list()
            logger.info("Found %d conversations", len(conversations))

            for i, conv_meta in enumerate(conversations, 1):
                conv_id = self._extract_conversation_id(conv_meta)
                if not conv_id:
                    logger.warning("Skipping conversation with missing ID: %s", conv_meta)
                    continue

                # Fetch full conversation details
                full_conv = self._fetch_conversation_detail(conv_id)
                if full_conv:
                    yield full_conv
                else:
                    # Fall back to metadata only
                    yield conv_meta

                if i % 10 == 0:
                    logger.info("Fetched %d/%d conversations...", i, len(conversations))

            logger.info("Finished fetching %d conversations", len(conversations))

        except requests.exceptions.RequestException as e:
            logger.error("Error fetching conversations: %s", e)
            raise
