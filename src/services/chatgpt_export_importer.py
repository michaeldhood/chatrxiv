"""
ChatGPT manual export importer.

Imports ChatGPT manual export files (conversations.json) into the normalized database.
Supports incremental import: when incremental=True, skips conversations whose
last_updated_at in the file is not newer than the stored chat.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from pydantic import ValidationError

from src.core.db import ChatDatabase
from src.core.models import Chat, ChatMode, Message, MessageRole, MessageType
from src.core.source_schemas.chatgpt import ChatGPTConversation
from src.readers.chatgpt_reader import ChatGPTReader

logger = logging.getLogger(__name__)


class ChatGPTExportImporter:
    """
    Imports ChatGPT manual export files into normalized database.
    
    Handles ChatGPT's export format (conversations.json) which contains
    a list of conversations with message tree structures.
    """
    
    def __init__(self, db: ChatDatabase):
        """
        Initialize importer.
        
        Parameters
        ----
        db : ChatDatabase
            Database instance
        """
        self.db = db
        # Create a ChatGPTReader instance to reuse its message flattening logic
        self.reader = ChatGPTReader()
    
    def import_file(
        self, file_path: Path, incremental: bool = False
    ) -> Dict[str, int]:
        """
        Import conversations from a ChatGPT export JSON file.

        Parameters
        ----
        file_path : Path
            Path to conversations.json file
        incremental : bool, optional
            If True, skip conversations that already exist and are not newer
            than the file's update_time. By default False.

        Returns
        ----
        Dict[str, int]
            Keys: "ingested" (number imported), "skipped" (unchanged when incremental)
        """
        if not file_path.exists():
            logger.error("File not found: %s", file_path)
            return {"ingested": 0, "skipped": 0}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                conversations = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to read/parse %s: %s", file_path, e)
            return {"ingested": 0, "skipped": 0}

        if not isinstance(conversations, list):
            logger.error("Expected list of conversations, got %s", type(conversations))
            return {"ingested": 0, "skipped": 0}

        ingested = 0
        skipped = 0

        for conv_data in conversations:
            try:
                try:
                    validated = ChatGPTConversation.model_validate(conv_data)
                    conv_data = validated.model_dump(mode="json", exclude_none=False)
                except ValidationError as ve:
                    logger.warning(
                        "Failed to validate ChatGPT conversation %s: %s. Using raw data.",
                        conv_data.get("conversation_id", "unknown"),
                        ve,
                    )

                chat = self._convert_conversation_to_chat(conv_data)
                if not chat:
                    continue

                if incremental:
                    existing = self.db.get_chat_by_composer_id(chat.cursor_composer_id)
                    if existing and chat.last_updated_at and existing.get("last_updated_at"):
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
                    "Failed to import conversation %s: %s",
                    conv_data.get("conversation_id", "unknown"),
                    e,
                )

        logger.info(
            "Imported %d chats from %s (skipped %d when incremental)",
            ingested,
            file_path,
            skipped,
        )
        return {"ingested": ingested, "skipped": skipped}
    
    def _convert_conversation_to_chat(self, conversation_data: Dict[str, Any]) -> Optional[Chat]:
        """
        Convert ChatGPT export conversation to Chat domain model.
        
        Parameters
        ----
        conversation_data : Dict[str, Any]
            Raw conversation from ChatGPT export
            
        Returns
        ----
        Chat or None
            Chat domain model, or None if conversion fails
        """
        conv_id = conversation_data.get("conversation_id")
        if not conv_id:
            return None
        
        # Extract title
        title = conversation_data.get("title", "Untitled Chat")
        
        # Extract timestamps
        created_at = self._parse_timestamp(conversation_data.get("create_time"))
        last_updated_at = self._parse_timestamp(conversation_data.get("update_time"))
        
        # Flatten message tree using ChatGPTReader's logic
        mapping = conversation_data.get("mapping", {})
        chat_messages = self.reader._flatten_message_tree(mapping)
        
        # Convert messages to domain model
        messages = []
        for msg_data in chat_messages:
            # Map sender to role
            sender = msg_data.get("sender", "")
            if sender == "user":
                role = MessageRole.USER
            elif sender == "assistant":
                role = MessageRole.ASSISTANT
            elif sender == "system":
                role = MessageRole.SYSTEM
            else:
                # Skip unknown types
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
            msg_created_at = self._parse_timestamp(msg_data.get("created_at"))
            
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
        
        if not messages:
            # Skip conversations with no messages
            return None
        
        # ChatGPT conversations are always chat mode
        mode = ChatMode.CHAT
        
        # Create chat
        chat = Chat(
            cursor_composer_id=conv_id,
            workspace_id=None,  # ChatGPT conversations don't have workspaces
            title=title,
            mode=mode,
            created_at=created_at,
            last_updated_at=last_updated_at,
            source="chatgpt",  # Important: mark as chatgpt source!
            messages=messages,
            relevant_files=[],  # ChatGPT export doesn't expose relevant files
        )
        
        return chat
    
    def _parse_timestamp(self, timestamp: Optional[Any]) -> Optional[datetime]:
        """
        Parse ChatGPT timestamp (supports both Unix epoch and ISO strings).
        
        Parameters
        ----
        timestamp : float, str, or None
            Timestamp value from ChatGPT export
            
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
                if timestamp.endswith('Z'):
                    timestamp = timestamp[:-1] + '+00:00'
                return datetime.fromisoformat(timestamp)
        except (ValueError, TypeError, OSError) as e:
            logger.debug("Could not parse ChatGPT timestamp %s: %s", timestamp, e)
        
        return None
    
    def import_zip(
        self, zip_path: Path, incremental: bool = False
    ) -> Dict[str, int]:
        """
        Import conversations from a ChatGPT export ZIP file.

        Extracts conversations.json from the ZIP and imports it.
        Uses Python's zipfile module first, falls back to macOS ditto if needed.

        Parameters
        ----
        zip_path : Path
            Path to ChatGPT export ZIP file
        incremental : bool, optional
            If True, skip conversations already in DB that are not newer than file.
            By default False.

        Returns
        ----
        Dict[str, int]
            Keys: "ingested", "skipped"
        """
        import platform
        import subprocess
        import tempfile
        import zipfile

        if not zip_path.exists():
            logger.error("ZIP file not found: %s", zip_path)
            return {"ingested": 0, "skipped": 0}

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    json_files = [
                        f
                        for f in zip_ref.namelist()
                        if f.endswith("conversations.json")
                    ]
                    if not json_files:
                        logger.error("No conversations.json found in ZIP file")
                        return {"ingested": 0, "skipped": 0}
                    conversations_json = json_files[0]
                    zip_ref.extract(conversations_json, temp_dir)
                    json_path = Path(temp_dir) / conversations_json
                    return self.import_file(json_path, incremental=incremental)
            except zipfile.BadZipFile:
                if platform.system() == "Darwin":
                    logger.info("Python zipfile failed, trying macOS ditto...")
                    try:
                        result = subprocess.run(
                            ["ditto", "-x", "-k", str(zip_path), temp_dir],
                            capture_output=True,
                            text=True,
                        )
                        conversations_json = None
                        for extracted_file in Path(temp_dir).rglob(
                            "conversations.json"
                        ):
                            conversations_json = extracted_file
                            break
                        if conversations_json and conversations_json.exists():
                            logger.info(
                                "Successfully extracted conversations.json using ditto"
                            )
                            return self.import_file(
                                conversations_json, incremental=incremental
                            )
                        if result.returncode != 0:
                            logger.warning("ditto reported errors: %s", result.stderr)
                        logger.error("No conversations.json found after extraction")
                        return {"ingested": 0, "skipped": 0}
                    except Exception as e:
                        logger.error(
                            "Error extracting ZIP file %s: %s", zip_path, e
                        )
                        return {"ingested": 0, "skipped": 0}
                logger.error(
                    "Invalid ZIP file: %s (and ditto not available on %s)",
                    zip_path,
                    platform.system(),
                )
                return {"ingested": 0, "skipped": 0}
            except Exception as e:
                logger.error(
                    "Error extracting ZIP file %s: %s", zip_path, e
                )
                return {"ingested": 0, "skipped": 0}