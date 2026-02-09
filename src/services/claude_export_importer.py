"""
Claude.ai file export importer.

Imports Claude.ai conversation exports from JSON files into the normalized
database. File format matches Claude API response shape: a single conversation
object or a list of conversation objects (uuid, name, updated_at, chat_messages, etc.).

Supports incremental import: when incremental=True, skips conversations whose
updated_at in the file is not newer than the stored chat.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from pydantic import ValidationError

from src.core.db import ChatDatabase
from src.core.models import Chat
from src.core.source_schemas.claude import ClaudeConversation
from src.transformers.claude import ClaudeTransformer

logger = logging.getLogger(__name__)


class ClaudeExportImporter:
    """
    Imports Claude.ai conversation export files into the normalized database.

    Accepts JSON in Claude API shape: single conversation object or list of
    conversation objects with uuid, name, created_at, updated_at, chat_messages.
    """

    def __init__(self, db: ChatDatabase):
        """
        Initialize importer.

        Parameters
        -------
        db : ChatDatabase
            Database instance
        """
        self.db = db
        self._transformer = ClaudeTransformer()

    def import_file(
        self, file_path: Path, incremental: bool = False
    ) -> Dict[str, int]:
        """
        Import conversations from a Claude export JSON file.

        Parameters
        -------
        file_path : Path
            Path to JSON file (single conversation object or list of objects)
        incremental : bool, optional
            If True, skip conversations that already exist and are not newer
            than the file's updated_at. By default False.

        Returns
        -------
        Dict[str, int]
            Keys: "ingested", "skipped"
        """
        if not file_path.exists():
            logger.error("File not found: %s", file_path)
            return {"ingested": 0, "skipped": 0}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to read/parse %s: %s", file_path, e)
            return {"ingested": 0, "skipped": 0}

        conversations = self._normalize_to_list(data)
        if not conversations:
            logger.warning("No conversation(s) found in %s", file_path)
            return {"ingested": 0, "skipped": 0}

        ingested = 0
        skipped = 0

        for conv_data in conversations:
            try:
                try:
                    validated = ClaudeConversation.model_validate(conv_data)
                    conv_data = validated.model_dump(mode="json", exclude_none=False)
                except ValidationError as ve:
                    logger.warning(
                        "Failed to validate Claude conversation %s: %s. Using raw.",
                        conv_data.get("uuid", "unknown"),
                        ve,
                    )

                chat = self._transformer.transform(conv_data)
                if not chat:
                    continue
                if not chat.messages:
                    skipped += 1
                    continue

                if incremental:
                    existing = self.db.get_chat_by_composer_id(chat.cursor_composer_id)
                    if (
                        existing
                        and chat.last_updated_at
                        and existing.get("last_updated_at")
                    ):
                        try:
                            db_updated = datetime.fromisoformat(
                                existing["last_updated_at"]
                            )
                            if chat.last_updated_at <= db_updated:
                                skipped += 1
                                continue
                        except (ValueError, TypeError):
                            pass

                self.db.upsert_chat(chat)
                ingested += 1
            except Exception as e:
                logger.error(
                    "Failed to import Claude conversation %s: %s",
                    conv_data.get("uuid", "unknown"),
                    e,
                )

        logger.info(
            "Imported %d Claude chats from %s (skipped %d when incremental)",
            ingested,
            file_path,
            skipped,
        )
        return {"ingested": ingested, "skipped": skipped}

    def _normalize_to_list(self, data: Any) -> List[Dict[str, Any]]:
        """
        Ensure we have a list of conversation dicts.

        Accepts a single conversation object or a list of conversation objects.
        """
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and data.get("uuid"):
            return [data]
        logger.warning("Unexpected root type or missing uuid: %s", type(data))
        return []
