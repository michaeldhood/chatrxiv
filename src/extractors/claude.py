"""
Claude.ai extractor for raw conversation data.

Extracts conversations from Claude.ai API and stores raw data in RawStorage.
Part of the ELT (Extract-Load-Transform) architecture.
"""

import logging
from typing import Any, Dict, Optional

from src.readers.claude_reader import ClaudeReader

from .base import BaseExtractor

logger = logging.getLogger(__name__)


class ClaudeExtractor(BaseExtractor):
    """
    Extractor for Claude.ai conversations.

    Fetches raw conversation data from Claude.ai API and stores it in
    RawStorage without transformation. Uses ClaudeReader for API access.

    Attributes
    ----------
    source_name : str
        Source identifier: 'claude.ai'
    reader : ClaudeReader
        Reader instance for fetching conversations from Claude.ai API

    Examples
    --------
    >>> from src.core.db.raw_storage import RawStorage
    >>> storage = RawStorage(db_path="data.db")
    >>> extractor = ClaudeExtractor(raw_storage=storage)
    >>> stats = extractor.extract_all()
    >>> print(f"Extracted {stats['extracted']} conversations")
    """

    def __init__(
        self,
        raw_storage,
        org_id: Optional[str] = None,
        session_cookie: Optional[str] = None,
    ):
        """
        Initialize Claude extractor.

        Parameters
        ----------
        raw_storage : RawStorage
            Storage instance for raw data
        org_id : str, optional
            Claude.ai organization ID. If None, resolves from env/dlt secrets.
        session_cookie : str, optional
            Claude.ai session cookie. If None, resolves from env/dlt secrets.
        """
        super().__init__(raw_storage)
        self.reader = ClaudeReader(org_id=org_id, session_cookie=session_cookie)

    @property
    def source_name(self) -> str:
        """
        Source identifier for Claude.ai.

        Returns
        -------
        str
            Source name: 'claude.ai'
        """
        return "claude.ai"

    def extract_all(
        self,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, int]:
        """
        Extract all Claude.ai conversations and store raw data.

        Iterates through all conversations, fetches full details, and stores
        them in RawStorage. Tracks statistics for extracted, skipped, and
        error cases.

        Parameters
        ----------
        progress_callback : callable, optional
            Callback(source_id, total, current) for progress updates

        Returns
        -------
        Dict[str, int]
            Statistics dictionary with keys:
            - 'extracted': number of successfully stored conversations
            - 'skipped': number of conversations skipped (already exists)
            - 'errors': number of conversations that failed to extract
        """
        stats = {"extracted": 0, "skipped": 0, "errors": 0}

        try:
            conversations = self.reader._fetch_conversation_list()
            total = len(conversations)
            logger.info("Found %d Claude.ai conversations", total)

            for i, conv_meta in enumerate(conversations, 1):
                try:
                    conv_id = self.reader._extract_conversation_id(conv_meta)
                    if not conv_id:
                        logger.warning(
                            "Skipping conversation with missing ID: %s", conv_meta
                        )
                        stats["errors"] += 1
                        continue

                    # Fetch full conversation details
                    full_conv = self.reader._fetch_conversation_detail(conv_id)
                    if not full_conv:
                        logger.warning(
                            "Failed to fetch details for conversation %s", conv_id
                        )
                        stats["errors"] += 1
                        continue

                    # Store raw data
                    try:
                        self._store_raw(source_id=conv_id, raw_data=full_conv)
                        stats["extracted"] += 1
                        logger.debug("Extracted conversation %s", conv_id)
                    except Exception as e:
                        # Check if it's a duplicate (already exists)
                        if "UNIQUE constraint" in str(e) or "already exists" in str(e):
                            stats["skipped"] += 1
                            logger.debug("Skipped duplicate conversation %s", conv_id)
                        else:
                            raise

                    # Progress callback
                    if progress_callback:
                        progress_callback(conv_id, total, i)

                except Exception as e:
                    logger.error(
                        "Error extracting conversation %s: %s",
                        conv_meta.get("uuid", "unknown"),
                        e,
                    )
                    stats["errors"] += 1

            logger.info(
                "Extraction complete: %d extracted, %d skipped, %d errors",
                stats["extracted"],
                stats["skipped"],
                stats["errors"],
            )

        except Exception as e:
            logger.error("Error fetching conversation list: %s", e)
            raise

        return stats

    def extract_one(self, source_id: str) -> Optional[Dict[str, Any]]:
        """
        Extract a single Claude.ai conversation by UUID.

        Fetches full conversation details and stores raw data in RawStorage.
        Returns the raw data dictionary if successful.

        Parameters
        ----------
        source_id : str
            Claude.ai conversation UUID

        Returns
        -------
        Dict[str, Any] or None
            Raw conversation data dictionary if found and stored successfully,
            None if conversation not found or extraction failed

        Examples
        --------
        >>> extractor = ClaudeExtractor(raw_storage=storage)
        >>> raw_data = extractor.extract_one("conv-uuid-123")
        >>> if raw_data:
        ...     print(f"Extracted conversation: {raw_data.get('name', 'Untitled')}")
        """
        try:
            # Fetch full conversation details
            full_conv = self.reader._fetch_conversation_detail(source_id)
            if not full_conv:
                logger.warning("Conversation %s not found", source_id)
                return None

            # Store raw data
            try:
                self._store_raw(source_id=source_id, raw_data=full_conv)
                logger.info("Extracted conversation %s", source_id)
                return full_conv
            except Exception as e:
                # If already exists, return the data anyway
                if "UNIQUE constraint" in str(e) or "already exists" in str(e):
                    logger.debug("Conversation %s already exists, returning data", source_id)
                    return full_conv
                raise

        except Exception as e:
            logger.error("Error extracting conversation %s: %s", source_id, e)
            return None
