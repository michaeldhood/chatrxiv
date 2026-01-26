"""
Cursor transformer for converting raw Cursor composer data to Chat domain models.

Part of the ELT (Extract-Load-Transform) architecture. Transforms raw composer
data from RawStorage into normalized Chat models for domain database storage.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from src.core.models import Chat, ChatMode, Message, MessageRole, MessageType
from src.core.source_schemas.cursor import Bubble, ComposerData, ComposerHead
from src.readers.global_reader import GlobalComposerReader
from src.transformers.base import BaseTransformer

logger = logging.getLogger(__name__)


class CursorTransformer(BaseTransformer):
    """
    Transformer for Cursor composer data.

    Converts raw composer data from Cursor's storage format to Chat domain models.
    Handles both old-style conversation arrays and new-style fullConversationHeadersOnly
    formats with split bubble storage.

    Attributes
    ----------
    global_reader : GlobalComposerReader, optional
        Reader for resolving bubble headers in split storage format.
        If None, headers-only format will fallback to header-only bubbles.
    """

    def __init__(
        self,
        raw_storage,
        domain_db,
        global_reader: Optional[GlobalComposerReader] = None,
    ):
        """
        Initialize Cursor transformer.

        Parameters
        ----------
        raw_storage : RawStorage
            Storage containing raw extracted data
        domain_db : ChatDatabase
            Domain database for storing transformed data
        global_reader : GlobalComposerReader, optional
            Reader for resolving bubble headers. If None, split storage format
            will use header-only bubbles (no text content).
        """
        super().__init__(raw_storage, domain_db)
        self.global_reader = global_reader

    @property
    def source_name(self) -> str:
        """
        Source identifier matching the extractor.

        Returns
        -------
        str
            Source name: 'cursor'
        """
        return "cursor"

    def transform(self, raw_data: Dict[str, Any]) -> Optional[Chat]:
        """
        Transform raw composer data to a Chat domain model.

        The raw_data structure from RawStorage is:
        {
            "composer_id": "...",
            "data": {...}  # Actual composer data
        }

        Parameters
        ----------
        raw_data : Dict[str, Any]
            Raw data from RawStorage (the 'raw_data' field)

        Returns
        -------
        Chat or None
            Transformed Chat model, or None if transformation fails
        """
        # Extract composer data from raw_data structure
        composer_data = raw_data.get("data")
        if not composer_data:
            logger.warning("Raw data missing 'data' field: %s", raw_data.keys())
            return None

        composer_id = raw_data.get("composer_id")
        if not composer_id:
            logger.warning("Raw data missing 'composer_id' field")
            return None

        # Extract workspace_id if present
        workspace_id = raw_data.get("workspace_id")

        # Extract composer_head if present (for title enrichment)
        composer_head = raw_data.get("composer_head")

        return self._convert_composer_to_chat(
            composer_data=composer_data,
            workspace_id=workspace_id,
            composer_head=composer_head,
        )

    def _convert_composer_to_chat(
        self,
        composer_data: Dict[str, Any],
        workspace_id: Optional[int] = None,
        composer_head: Optional[Dict[str, Any]] = None,
    ) -> Optional[Chat]:
        """
        Convert Cursor composer data to Chat domain model.

        Uses Pydantic source models for validation. Falls back to dict parsing
        if validation fails (for schema drift resilience).

        Parameters
        ----
        composer_data : Dict[str, Any]
            Raw composer data from global database
        workspace_id : int, optional
            Workspace ID if known
        composer_head : Dict[str, Any], optional
            Composer head metadata from workspace (for title enrichment)

        Returns
        ----
        Chat
            Chat domain model, or None if conversion fails
        """
        # Validate composer data with Pydantic model
        try:
            composer = ComposerData.model_validate(composer_data)
            composer_id = composer.composerId
        except ValidationError as e:
            # Fallback to dict parsing if validation fails (schema drift)
            logger.warning(
                "ComposerData validation failed for composer %s: %s. Falling back to dict parsing.",
                composer_data.get("composerId", "unknown"),
                str(e),
            )
            composer_id = composer_data.get("composerId")
            if not composer_id:
                return None
            composer = None  # Use dict fallback

        # Validate composer head if provided
        validated_head = None
        if composer_head:
            try:
                validated_head = ComposerHead.model_validate(composer_head)
            except ValidationError as e:
                logger.debug(
                    "ComposerHead validation failed: %s. Using dict fallback.",
                    str(e),
                )
                # Continue with dict fallback

        # Determine mode (prefer workspace head, then global data)
        force_mode = None
        unified_mode = None

        if validated_head:
            force_mode = validated_head.forceMode
            unified_mode = validated_head.unifiedMode
        elif composer_head:
            # Fallback to dict access
            force_mode = composer_head.get("forceMode")
            unified_mode = composer_head.get("unifiedMode")

        if not force_mode and composer:
            force_mode = composer.forceMode
        elif not force_mode:
            force_mode = composer_data.get("forceMode", "chat")

        if not unified_mode and composer:
            unified_mode = composer.unifiedMode
        elif not unified_mode:
            unified_mode = composer_data.get("unifiedMode", "chat")

        mode_map = {
            "chat": ChatMode.CHAT,
            "edit": ChatMode.EDIT,
            "agent": ChatMode.AGENT,
            "composer": ChatMode.COMPOSER,
            "plan": ChatMode.PLAN,
            "debug": ChatMode.DEBUG,
            "ask": ChatMode.ASK,
        }
        mode = mode_map.get(force_mode or unified_mode, ChatMode.CHAT)

        # Extract title with enrichment priority:
        # 1. workspace composer head name
        # 2. workspace composer head subtitle
        # 3. global composer data name/subtitle
        # 4. fallback
        title = None
        if validated_head:
            title = validated_head.name or validated_head.subtitle
        elif composer_head:
            title = composer_head.get("name") or composer_head.get("subtitle")

        if not title and composer:
            title = composer.name or composer.subtitle
        elif not title:
            title = composer_data.get("name") or composer_data.get("subtitle")

        if not title:
            title = "Untitled Chat"

        # Extract timestamps (prefer workspace head, then global data)
        created_at = None
        if validated_head and validated_head.createdAt:
            try:
                created_at = datetime.fromtimestamp(validated_head.createdAt / 1000)
            except (ValueError, TypeError):
                pass
        elif composer_head and composer_head.get("createdAt"):
            try:
                created_at = datetime.fromtimestamp(composer_head["createdAt"] / 1000)
            except (ValueError, TypeError):
                pass

        if not created_at and composer and composer.createdAt:
            try:
                created_at = datetime.fromtimestamp(composer.createdAt / 1000)
            except (ValueError, TypeError):
                pass
        elif not created_at and composer_data.get("createdAt"):
            try:
                created_at = datetime.fromtimestamp(composer_data["createdAt"] / 1000)
            except (ValueError, TypeError):
                pass

        last_updated_at = None
        if validated_head and validated_head.lastUpdatedAt:
            try:
                last_updated_at = datetime.fromtimestamp(
                    validated_head.lastUpdatedAt / 1000
                )
            except (ValueError, TypeError):
                pass
        elif composer_head and composer_head.get("lastUpdatedAt"):
            try:
                last_updated_at = datetime.fromtimestamp(
                    composer_head["lastUpdatedAt"] / 1000
                )
            except (ValueError, TypeError):
                pass

        if not last_updated_at and composer and composer.lastUpdatedAt:
            try:
                last_updated_at = datetime.fromtimestamp(composer.lastUpdatedAt / 1000)
            except (ValueError, TypeError):
                pass
        elif not last_updated_at and composer_data.get("lastUpdatedAt"):
            try:
                last_updated_at = datetime.fromtimestamp(
                    composer_data["lastUpdatedAt"] / 1000
                )
            except (ValueError, TypeError):
                pass

        # Extract conversation - try multiple formats
        # Format 1: Old style with full conversation array
        conversation = []
        if composer:
            if composer.conversation:
                # Legacy inline format
                conversation = [bubble.model_dump() for bubble in composer.conversation]
            elif composer.fullConversationHeadersOnly:
                # Modern split format - resolve headers
                headers_dict = [
                    header.model_dump() for header in composer.fullConversationHeadersOnly
                ]
                conversation = self._resolve_conversation_from_headers(
                    composer_id, headers_dict
                )
        else:
            # Fallback to dict parsing
            conversation = composer_data.get("conversation", [])
            if not conversation:
                headers = composer_data.get("fullConversationHeadersOnly", [])
                if headers:
                    conversation = self._resolve_conversation_from_headers(
                        composer_id, headers
                    )

        messages = []
        relevant_files = set()

        for bubble_data in conversation:
            # Validate bubble if it's a dict, otherwise assume it's already validated
            bubble_dict = None
            validated_bubble = None

            if isinstance(bubble_data, dict):
                # Try to validate as Bubble model
                try:
                    validated_bubble = Bubble.model_validate(bubble_data)
                    bubble_dict = validated_bubble.model_dump()
                except ValidationError:
                    # Fallback to dict parsing
                    bubble_dict = bubble_data
            else:
                # Already a Bubble model
                validated_bubble = bubble_data
                bubble_dict = validated_bubble.model_dump()

            # Use validated model if available, otherwise dict
            if validated_bubble:
                bubble_type = validated_bubble.type
                text = validated_bubble.text or ""
                rich_text = validated_bubble.richText or ""
                bubble_id = validated_bubble.bubbleId
                # Extract thinking content
                if not text and validated_bubble.thinking:
                    text = validated_bubble.thinking.text or ""
                # Extract timestamp
                msg_created_at = None
                if validated_bubble.createdAt:
                    try:
                        # Bubble.createdAt is ISO string, need to parse
                        msg_created_at = datetime.fromisoformat(
                            validated_bubble.createdAt.replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass
            else:
                # Dict fallback
                bubble_type = bubble_dict.get("type")
                text = bubble_dict.get("text", "")
                rich_text = bubble_dict.get("richText", "")
                bubble_id = bubble_dict.get("bubbleId")
                # Extract thinking content
                if not text:
                    thinking_data = bubble_dict.get("thinking")
                    if thinking_data and isinstance(thinking_data, dict):
                        thinking_text = thinking_data.get("text", "")
                        if thinking_text:
                            text = thinking_text
                # Extract timestamp
                msg_created_at = None
                if bubble_dict.get("createdAt"):
                    # Could be ISO string or Unix timestamp
                    created_at_val = bubble_dict["createdAt"]
                    if isinstance(created_at_val, (int, float)):
                        try:
                            msg_created_at = datetime.fromtimestamp(created_at_val / 1000)
                        except (ValueError, TypeError):
                            pass
                    elif isinstance(created_at_val, str):
                        try:
                            msg_created_at = datetime.fromisoformat(
                                created_at_val.replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            pass

            if bubble_type == 1:  # User message
                role = MessageRole.USER
            elif bubble_type == 2:  # AI response
                role = MessageRole.ASSISTANT
            else:
                continue  # Skip unknown types

            # Classify the bubble type (use dict for classification logic)
            message_type = self._classify_bubble(bubble_dict)

            message = Message(
                role=role,
                text=text,
                rich_text=rich_text,
                created_at=msg_created_at or created_at,  # Fallback to chat created_at
                cursor_bubble_id=bubble_id,
                raw_json=bubble_dict,  # Store original dict for compatibility
                message_type=message_type,
            )
            messages.append(message)

            # Extract relevant files (not in Bubble model, check dict)
            if bubble_dict:
                for file_path in bubble_dict.get("relevantFiles", []):
                    relevant_files.add(file_path)

        # Create chat
        chat = Chat(
            cursor_composer_id=composer_id,
            workspace_id=workspace_id,
            title=title,
            mode=mode,
            created_at=created_at,
            last_updated_at=last_updated_at,
            source="cursor",
            messages=messages,
            relevant_files=list(relevant_files),
        )

        return chat

    def _resolve_conversation_from_headers(
        self, composer_id: str, headers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Resolve conversation bubbles from headers-only format.

        In newer Cursor versions, conversation data is split:
        - fullConversationHeadersOnly: list of {bubbleId, type} headers
        - Actual content stored separately as bubbleId:{composerId}:{bubbleId} keys

        Uses batch query for efficiency when multiple bubbles need to be fetched.

        Parameters
        ----
        composer_id : str
            Composer UUID
        headers : List[Dict[str, Any]]
            List of bubble headers with bubbleId and type

        Returns
        ----
        List[Dict[str, Any]]
            List of full bubble objects with text/richText content
        """
        # Extract all bubble IDs
        bubble_ids = [
            header.get("bubbleId") for header in headers if header.get("bubbleId")
        ]

        # Batch fetch all bubbles in one query (if global_reader available)
        bubbles_map = {}
        if self.global_reader:
            bubbles_map = self.global_reader.read_bubbles_batch(composer_id, bubble_ids)
        else:
            logger.debug(
                "GlobalComposerReader not available, using header-only bubbles for composer %s",
                composer_id,
            )

        # Build conversation list, preserving header order
        conversation = []
        for header in headers:
            bubble_id = header.get("bubbleId")
            if not bubble_id:
                continue

            bubble_data = bubbles_map.get(bubble_id)
            if bubble_data:
                # Merge header info (type) with full bubble data
                bubble = {**bubble_data}
                # Ensure type is present (from header if not in bubble)
                if "type" not in bubble:
                    bubble["type"] = header.get("type")
                conversation.append(bubble)
            else:
                # Fallback: use header only (will have no text)
                conversation.append(header)

        return conversation

    def _classify_bubble(self, bubble: Dict[str, Any]) -> MessageType:
        """
        Classify a bubble by its content type.

        Parameters
        ----
        bubble : Dict[str, Any]
            Raw bubble data from Cursor

        Returns
        ----
        MessageType
            Classification of the bubble content
        """
        text = bubble.get("text", "")
        rich_text = bubble.get("richText", "")

        # Has content -> response
        if text or rich_text:
            return MessageType.RESPONSE

        # Check for tool-related fields
        # Cursor stores tool calls with various metadata fields
        # toolFormerData contains tool execution info (name, params, result)
        # toolFormerResult contains execution results
        if (
            bubble.get("codeBlock")
            or bubble.get("toolFormerData")
            or bubble.get("toolFormerResult")
            or bubble.get("toolCalls")
            or bubble.get("toolCall")
        ):
            return MessageType.TOOL_CALL

        # Check for thinking/reasoning metadata
        # This is less common but may exist in some formats
        if bubble.get("thinking") or bubble.get("reasoning"):
            return MessageType.THINKING

        # Default empty
        return MessageType.EMPTY
