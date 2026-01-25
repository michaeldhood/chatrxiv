"""
ChatGPT extractor for raw data extraction from export files.

Extracts raw conversation data from ChatGPT export files (conversations.json)
and stores it in RawStorage. This is pure extraction - no transformation.
"""

import json
import logging
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class ChatGPTExtractor(BaseExtractor):
    """
    Extractor for ChatGPT conversations from export files.

    Reads conversations from ChatGPT export files (conversations.json or ZIP
    files containing conversations.json) and stores raw data in RawStorage.

    Parameters
    ----
    raw_storage : RawStorage
        Storage instance for raw data
    export_path : Path, optional
        Path to conversations.json file or ZIP file containing it.
        If None, extractor will not be able to extract data.
    """

    def __init__(self, raw_storage, export_path: Optional[Path] = None):
        """
        Initialize ChatGPT extractor.

        Parameters
        ----
        raw_storage : RawStorage
            Storage instance for raw data
        export_path : Path, optional
            Path to conversations.json file or ZIP file containing it
        """
        super().__init__(raw_storage)
        self.export_path = Path(export_path) if export_path else None
        self._conversations_cache: Optional[List[Dict[str, Any]]] = None

    @property
    def source_name(self) -> str:
        """
        Source identifier for ChatGPT.

        Returns
        ----
        str
            Source name: 'chatgpt'
        """
        return "chatgpt"

    def _load_conversations(self) -> List[Dict[str, Any]]:
        """
        Load conversations from export file.

        Handles both direct JSON files and ZIP files containing conversations.json.

        Returns
        ----
        List[Dict[str, Any]]
            List of conversation dictionaries

        Raises
        ---
        FileNotFoundError
            If export_path is not set or file doesn't exist
        ValueError
            If file format is invalid or conversations.json not found
        """
        if not self.export_path:
            raise ValueError("export_path not set. Cannot load conversations.")

        if not self.export_path.exists():
            raise FileNotFoundError(f"Export file not found: {self.export_path}")

        # Check if it's a ZIP file
        if self.export_path.suffix.lower() == ".zip":
            return self._load_from_zip(self.export_path)

        # Otherwise, treat as JSON file
        if self.export_path.name != "conversations.json":
            logger.warning(
                "Expected conversations.json, got %s. Attempting to read anyway.",
                self.export_path.name,
            )

        try:
            with open(self.export_path, "r", encoding="utf-8") as f:
                conversations = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {self.export_path}: {e}") from e

        if not isinstance(conversations, list):
            raise ValueError(
                f"Expected list of conversations, got {type(conversations)}"
            )

        return conversations

    def _load_from_zip(self, zip_path: Path) -> List[Dict[str, Any]]:
        """
        Load conversations.json from a ZIP file.

        Parameters
        ----
        zip_path : Path
            Path to ZIP file

        Returns
        ----
        List[Dict[str, Any]]
            List of conversation dictionaries

        Raises
        ---
        ValueError
            If conversations.json not found in ZIP or invalid format
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                # Look for conversations.json in the ZIP
                json_files = [
                    f for f in zip_ref.namelist() if f.endswith("conversations.json")
                ]

                if not json_files:
                    raise ValueError(
                        f"No conversations.json found in ZIP file: {zip_path}"
                    )

                # Extract and read the first conversations.json found
                conversations_json = json_files[0]
                with zip_ref.open(conversations_json) as f:
                    conversations = json.load(f)

                if not isinstance(conversations, list):
                    raise ValueError(
                        f"Expected list of conversations, got {type(conversations)}"
                    )

                return conversations

        except zipfile.BadZipFile as e:
            raise ValueError(f"Invalid ZIP file: {zip_path}") from e

    def _get_conversations(self) -> List[Dict[str, Any]]:
        """
        Get conversations, using cache if available.

        Returns
        ----
        List[Dict[str, Any]]
            List of conversation dictionaries
        """
        if self._conversations_cache is None:
            self._conversations_cache = self._load_conversations()
        return self._conversations_cache

    def extract_all(
        self,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, int]:
        """
        Extract all conversations from export file and store in RawStorage.

        Parameters
        ----
        progress_callback : callable, optional
            Callback(source_id, total, current) for progress updates

        Returns
        ----
        Dict[str, int]
            Statistics: {'extracted': count, 'skipped': count, 'errors': count}
        """
        stats = {"extracted": 0, "skipped": 0, "errors": 0}

        try:
            conversations = self._get_conversations()
            total = len(conversations)

            logger.info("Extracting %d conversations from %s", total, self.export_path)

            for idx, conv_data in enumerate(conversations, start=1):
                try:
                    # Extract conversation ID (ChatGPT uses 'conversation_id' or 'id')
                    source_id = conv_data.get("conversation_id") or conv_data.get("id")

                    if not source_id:
                        logger.warning(
                            "Skipping conversation without ID at index %d", idx - 1
                        )
                        stats["skipped"] += 1
                        continue

                    # Store raw conversation data
                    self._store_raw(str(source_id), conv_data)
                    stats["extracted"] += 1

                    if progress_callback:
                        progress_callback(source_id, total, idx)

                except Exception as e:
                    logger.error(
                        "Error extracting conversation at index %d: %s", idx - 1, e
                    )
                    stats["errors"] += 1

            logger.info(
                "Extraction complete: %d extracted, %d skipped, %d errors",
                stats["extracted"],
                stats["skipped"],
                stats["errors"],
            )

        except Exception as e:
            logger.error("Failed to extract conversations: %s", e)
            stats["errors"] += 1

        return stats

    def extract_one(self, source_id: str) -> Optional[Dict[str, Any]]:
        """
        Extract a single conversation by its ID.

        Parameters
        ----
        source_id : str
            Conversation ID to extract

        Returns
        ----
        Dict or None
            Raw conversation data if found, None otherwise
        """
        try:
            conversations = self._get_conversations()

            for conv_data in conversations:
                # Check both 'conversation_id' and 'id' fields
                conv_id = conv_data.get("conversation_id") or conv_data.get("id")

                if conv_id and str(conv_id) == source_id:
                    # Store raw data before returning
                    self._store_raw(source_id, conv_data)
                    return conv_data

            logger.debug("Conversation %s not found in export file", source_id)
            return None

        except Exception as e:
            logger.error("Error extracting conversation %s: %s", source_id, e)
            return None
