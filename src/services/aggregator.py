"""
Chat aggregator service.

Orchestrates extraction from Cursor databases, linking workspace metadata
to global composer conversations, and storing normalized data.

Also supports ELT (Extract-Load-Transform) pipeline using extractors and
transformers for raw data preservation and re-transformation.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import ValidationError

from src.core.db import ChatDatabase
from src.core.db.raw_storage import RawStorage
from src.core.models import Chat, ChatMode, Message, MessageRole, MessageType, Workspace
from src.core.source_schemas.cursor import Bubble, ComposerData, ComposerHead
from src.extractors import (
    ChatGPTExtractor,
    ClaudeCodeExtractor,
    ClaudeExtractor,
    CursorExtractor,
)
from src.readers import ChatGPTReader, ClaudeReader
from src.readers.claude_code_reader import ClaudeCodeReader
from src.readers.global_reader import GlobalComposerReader
from src.readers.plan_reader import PlanRegistryReader
from src.readers.workspace_reader import WorkspaceStateReader
from src.transformers import (
    ChatGPTTransformer,
    ClaudeCodeTransformer,
    ClaudeTransformer,
    CursorTransformer,
)

logger = logging.getLogger(__name__)


@dataclass
class WebSourceConfig:
    """Configuration for web-based conversation source ingestion."""

    name: str  # "claude" or "chatgpt"
    reader_class: type  # ClaudeReader or ChatGPTReader
    id_field: str  # "uuid" or "id"
    updated_field: str  # "updated_at" or "update_time"
    converter: Callable  # Conversion method reference
    timestamp_parser: Callable  # Timestamp parsing method


class ChatAggregator:
    """
    Aggregates chats from Cursor databases into normalized local database.

    Handles:
    - Reading workspace metadata
    - Reading global composer conversations
    - Linking composers to workspaces
    - Converting to domain models
    - Storing in local database

    Also supports ELT pipeline:
    - extract(source): Extract raw data to RawStorage
    - transform(source): Transform raw data to domain models
    - ingest_elt(source): Full ELT pipeline (extract + transform)
    """

    # Valid source names for ELT operations
    VALID_SOURCES = ("cursor", "claude.ai", "chatgpt", "claude-code")

    def __init__(self, db: ChatDatabase, raw_storage: Optional[RawStorage] = None):
        """
        Initialize aggregator.

        Parameters
        ----------
        db : ChatDatabase
            Database instance for storing aggregated data
        raw_storage : RawStorage, optional
            Raw storage instance for ELT operations. If None, ELT methods
            will create a default RawStorage instance when called.
        """
        self.db = db
        self._raw_storage = raw_storage
        self.workspace_reader = WorkspaceStateReader()
        self.global_reader = GlobalComposerReader()
        self.plan_reader = PlanRegistryReader()

        # Lazy-initialized extractors and transformers
        self._extractors: Optional[Dict[str, Any]] = None
        self._transformers: Optional[Dict[str, Any]] = None

    @property
    def raw_storage(self) -> RawStorage:
        """Get or create RawStorage instance."""
        if self._raw_storage is None:
            self._raw_storage = RawStorage()
        return self._raw_storage

    def _get_extractors(self) -> Dict[str, Any]:
        """Lazy-initialize extractors."""
        if self._extractors is None:
            self._extractors = {
                "cursor": CursorExtractor(self.raw_storage),
                "claude.ai": ClaudeExtractor(self.raw_storage),
                "chatgpt": ChatGPTExtractor(self.raw_storage),
                "claude-code": ClaudeCodeExtractor(self.raw_storage),
            }
        return self._extractors

    def _get_transformers(self) -> Dict[str, Any]:
        """Lazy-initialize transformers."""
        if self._transformers is None:
            self._transformers = {
                "cursor": CursorTransformer(
                    self.raw_storage, self.db, global_reader=self.global_reader
                ),
                "claude.ai": ClaudeTransformer(self.raw_storage, self.db),
                "chatgpt": ChatGPTTransformer(self.raw_storage, self.db),
                "claude-code": ClaudeCodeTransformer(self.raw_storage, self.db),
            }
        return self._transformers

    def extract(
        self,
        source: str,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, int]:
        """
        Extract raw data from a source and store in RawStorage.

        This is the 'E' in ELT - pure extraction without transformation.

        Parameters
        ----------
        source : str
            Source identifier: 'cursor', 'claude.ai', 'chatgpt', 'claude-code'
        progress_callback : callable, optional
            Callback(source_id, total, current) for progress updates

        Returns
        -------
        Dict[str, int]
            Statistics: {'extracted': count, 'skipped': count, 'errors': count}

        Raises
        ------
        ValueError
            If source is not a valid source identifier
        """
        if source not in self.VALID_SOURCES:
            raise ValueError(
                f"Invalid source '{source}'. Valid sources: {self.VALID_SOURCES}"
            )

        logger.info("Starting extraction for source: %s", source)
        extractor = self._get_extractors()[source]
        stats = extractor.extract_all(progress_callback=progress_callback)
        logger.info(
            "Extraction complete for %s: %d extracted, %d skipped, %d errors",
            source,
            stats.get("extracted", 0),
            stats.get("skipped", 0),
            stats.get("errors", 0),
        )
        return stats

    def transform(
        self,
        source: str,
        incremental: bool = False,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, int]:
        """
        Transform raw data from RawStorage to domain models.

        This is the 'T' in ELT - reads from RawStorage and writes to domain DB.

        Parameters
        ----------
        source : str
            Source identifier: 'cursor', 'claude.ai', 'chatgpt', 'claude-code'
        incremental : bool
            If True, only transform data extracted since last transform
        progress_callback : callable, optional
            Callback(source_id, total, current) for progress updates

        Returns
        -------
        Dict[str, int]
            Statistics: {'transformed': count, 'skipped': count, 'errors': count}

        Raises
        ------
        ValueError
            If source is not a valid source identifier
        """
        if source not in self.VALID_SOURCES:
            raise ValueError(
                f"Invalid source '{source}'. Valid sources: {self.VALID_SOURCES}"
            )

        logger.info(
            "Starting transformation for source: %s (incremental=%s)",
            source,
            incremental,
        )
        transformer = self._get_transformers()[source]
        stats = transformer.transform_all(
            incremental=incremental,
            progress_callback=progress_callback,
        )
        logger.info(
            "Transformation complete for %s: %d transformed, %d skipped, %d errors",
            source,
            stats.get("transformed", 0),
            stats.get("skipped", 0),
            stats.get("errors", 0),
        )
        return stats

    def ingest_elt(
        self,
        source: str,
        incremental: bool = False,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, int]:
        """
        Full ELT pipeline: Extract raw data, then Transform to domain models.

        Combines extract() and transform() in one operation.

        Parameters
        ----------
        source : str
            Source identifier: 'cursor', 'claude.ai', 'chatgpt', 'claude-code'
        incremental : bool
            If True, only process new/updated data
        progress_callback : callable, optional
            Callback(source_id, total, current) for progress updates

        Returns
        -------
        Dict[str, int]
            Combined statistics from extraction and transformation
        """
        logger.info("Starting ELT pipeline for source: %s", source)

        # Extract
        extract_stats = self.extract(source, progress_callback=progress_callback)

        # Transform
        transform_stats = self.transform(
            source,
            incremental=incremental,
            progress_callback=progress_callback,
        )

        # Combine stats
        combined_stats = {
            "extracted": extract_stats.get("extracted", 0),
            "extract_skipped": extract_stats.get("skipped", 0),
            "extract_errors": extract_stats.get("errors", 0),
            "transformed": transform_stats.get("transformed", 0),
            "transform_skipped": transform_stats.get("skipped", 0),
            "transform_errors": transform_stats.get("errors", 0),
        }

        logger.info(
            "ELT pipeline complete for %s: %d extracted, %d transformed",
            source,
            combined_stats["extracted"],
            combined_stats["transformed"],
        )

        return combined_stats

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

        # Batch fetch all bubbles in one query
        bubbles_map = self.global_reader.read_bubbles_batch(composer_id, bubble_ids)

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

    def _find_project_root(self, file_path: str) -> Optional[str]:
        """
        Find project root (git root or common project directory) from a file path.

        Tries multiple strategies:
        1. Walk up directory tree looking for .git or project markers (if path exists)
        2. Infer from path structure (e.g., /workspace/project -> /workspace/project)
        3. Use parent directory as fallback

        Parameters
        ----
        file_path : str
            Absolute file path

        Returns
        ----
        str, optional
            Project root path as file:// URI, or None if not found
        """
        try:
            path = Path(file_path)
            if not path.is_absolute():
                return None

            # Strategy 1: If path exists, walk up looking for git/project markers
            if path.exists() or path.parent.exists():
                current = path.parent if path.is_file() else path
                while current != current.parent:  # Stop at filesystem root
                    # Check for .git directory
                    if (current / ".git").exists():
                        return f"file://{current}"

                    # Check for common project markers
                    if (
                        (current / "package.json").exists()
                        or (current / "pyproject.toml").exists()
                        or (current / "setup.py").exists()
                        or (current / "Cargo.toml").exists()
                        or (current / "go.mod").exists()
                    ):
                        return f"file://{current}"

                    current = current.parent

            # Strategy 2: Infer from path structure
            # For paths like /workspace/project/..., infer /workspace/project
            # For paths like /Users/.../project/..., infer project root
            parts = path.parts
            if len(parts) >= 3:
                # Look for common workspace/project patterns
                # /workspace/project/... -> /workspace/project
                if parts[1] == "workspace" and len(parts) >= 3:
                    inferred_root = Path("/") / parts[1] / parts[2]
                    return f"file://{inferred_root}"

                # /Users/.../git/project/... -> find project directory
                # Walk up to find a directory that looks like a project root
                current = path.parent if path.is_file() else path
                # Go up a few levels to find likely project root
                for _ in range(5):  # Check up to 5 levels up
                    if current == current.parent:
                        break
                    # Heuristic: if directory name looks like a project (not generic)
                    if current.name and current.name not in [
                        "sources",
                        "src",
                        "lib",
                        "dlt",
                    ]:
                        # Check if parent has common project structure indicators
                        parent_parts = current.parts
                        if len(parent_parts) >= 2:
                            # If we're in something like /.../git/project, return project
                            if "git" in parent_parts or "workspace" in parent_parts:
                                return f"file://{current}"
                    current = current.parent

            # Strategy 3: Fallback - use parent directory
            if path.is_file():
                return f"file://{path.parent}"

            return None

        except (OSError, ValueError) as e:
            logger.debug("Error finding project root for %s: %s", file_path, e)
            return None

    def _extract_path_from_uri(self, uri: Any) -> Optional[str]:
        """
        Extract file path from various URI formats.

        Parameters
        ----
        uri : Any
            URI as dict, string, or other format

        Returns
        ----
        str, optional
            File path, or None if not extractable
        """
        if isinstance(uri, dict):
            return (
                uri.get("fsPath")
                or uri.get("path")
                or uri.get("external", "").replace("file://", "")
            )
        elif isinstance(uri, str):
            if uri.startswith("file://"):
                return uri[7:]  # Remove "file://" prefix
            return uri
        return None

    def _infer_workspace_from_context(
        self, composer_data: Dict[str, Any]
    ) -> Optional[str]:
        """
        Extract workspace path from file selections in composer context.

        When workspace reference is missing (e.g., deleted multi-folder config),
        we can infer the workspace from file paths referenced in the conversation.

        Checks multiple sources:
        - context.fileSelections
        - context.folderSelections
        - context.selections
        - context.mentions.fileSelections
        - context.mentions.selections (JSON strings)
        - codeBlockData keys
        - newlyCreatedFiles array
        - originalFileStates keys

        Parameters
        ----
        composer_data : Dict[str, Any]
            Raw composer data from global database

        Returns
        ----
        str, optional
            Workspace path as file:// URI, or None if not inferrable
        """
        context = composer_data.get("context", {})
        if not isinstance(context, dict):
            return None

        # Helper to try a path and return if successful
        def try_path(path: Optional[str]) -> Optional[str]:
            if not path:
                return None
            # Remove file:// prefix if present
            clean_path = (
                path.replace("file://", "") if path.startswith("file://") else path
            )
            project_root = self._find_project_root(clean_path)
            return project_root

        # 1. Check context.fileSelections (most reliable)
        file_selections = context.get("fileSelections", [])
        if file_selections:
            for fs in file_selections:
                if not isinstance(fs, dict):
                    continue
                uri = fs.get("uri", {})
                path = self._extract_path_from_uri(uri)
                result = try_path(path)
                if result:
                    return result

        # 2. Check context.folderSelections
        folder_selections = context.get("folderSelections", [])
        if folder_selections:
            for fs in folder_selections:
                if not isinstance(fs, dict):
                    continue
                uri = fs.get("uri", {})
                path = self._extract_path_from_uri(uri)
                if path:
                    try:
                        abs_path = str(Path(path).resolve())
                        return f"file://{abs_path}"
                    except (OSError, ValueError):
                        pass

        # 3. Check context.selections
        selections = context.get("selections", [])
        if selections:
            for sel in selections:
                if not isinstance(sel, dict):
                    continue
                uri = sel.get("uri", {})
                path = self._extract_path_from_uri(uri)
                result = try_path(path)
                if result:
                    return result

        # 4. Check context.mentions.fileSelections (keys are file paths)
        mentions = context.get("mentions", {})
        if isinstance(mentions, dict):
            mentions_file_selections = mentions.get("fileSelections", {})
            if isinstance(mentions_file_selections, dict):
                for file_path in mentions_file_selections.keys():
                    result = try_path(file_path)
                    if result:
                        return result

            # 5. Check context.mentions.selections (values may be JSON strings with URIs)
            mentions_selections = mentions.get("selections", {})
            if isinstance(mentions_selections, dict):
                for key, value in mentions_selections.items():
                    # Key might be a JSON string with URI
                    if isinstance(key, str) and "uri" in key:
                        try:
                            import json

                            parsed = json.loads(key)
                            uri = parsed.get("uri", "")
                            path = self._extract_path_from_uri(uri)
                            result = try_path(path)
                            if result:
                                return result
                        except (json.JSONDecodeError, TypeError):
                            pass

        # 6. Check codeBlockData keys (file paths as dictionary keys)
        code_block_data = composer_data.get("codeBlockData", {})
        if isinstance(code_block_data, dict):
            for file_path in code_block_data.keys():
                result = try_path(file_path)
                if result:
                    return result

        # 7. Check newlyCreatedFiles array
        newly_created_files = composer_data.get("newlyCreatedFiles", [])
        if newly_created_files:
            for file_obj in newly_created_files:
                if isinstance(file_obj, dict):
                    uri = file_obj.get("uri", {})
                    path = self._extract_path_from_uri(uri)
                    result = try_path(path)
                    if result:
                        return result

        # 8. Check originalFileStates keys (file paths as dictionary keys)
        original_file_states = composer_data.get("originalFileStates", {})
        if isinstance(original_file_states, dict):
            for file_path in original_file_states.keys():
                result = try_path(file_path)
                if result:
                    return result

        return None

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

    def _load_workspace_data(
        self,
    ) -> Tuple[Dict[str, int], Dict[str, Optional[int]], Dict[str, Dict[str, Any]]]:
        """
        Load workspace data once and build all three mappings in a single pass.

        This method reads workspaces only once, avoiding redundant database opens.

        Returns
        ----
        tuple[Dict[str, int], Dict[str, Optional[int]], Dict[str, Dict[str, Any]]]
            Tuple of (workspace_map, composer_to_workspace, composer_heads)
            - workspace_map: workspace_hash -> workspace_id
            - composer_to_workspace: composer_id -> workspace_id (None if unknown)
            - composer_heads: composer_id -> composer head metadata
        """
        # Read all workspaces once
        workspaces_metadata = self.workspace_reader.read_all_workspaces()

        workspace_map = {}
        composer_to_workspace = {}
        composer_heads = {}

        # Build all three mappings in one pass
        for workspace_hash, metadata in workspaces_metadata.items():
            # Build workspace map
            # Use `or ""` because project_path can be None when workspace.json is missing
            project_path = metadata.get("project_path") or ""
            workspace = Workspace(
                workspace_hash=workspace_hash,
                folder_uri=project_path,
                resolved_path=project_path,
            )
            workspace_id = self.db.upsert_workspace(workspace)
            workspace_map[workspace_hash] = workspace_id

            # Extract composer data from metadata (already loaded, no need to re-read)
            composer_data = metadata.get("composer_data")
            if composer_data and isinstance(composer_data, dict):
                all_composers = composer_data.get("allComposers", [])

                for composer in all_composers:
                    composer_id = composer.get("composerId")
                    if composer_id:
                        # Build composer_to_workspace map
                        composer_to_workspace[composer_id] = workspace_id

                        # Build composer_heads map - validate if possible
                        try:
                            validated_head = ComposerHead.model_validate(composer)
                            composer_heads[composer_id] = validated_head.model_dump()
                        except ValidationError:
                            # Fallback to dict
                            composer_heads[composer_id] = {
                                "name": composer.get("name"),
                                "subtitle": composer.get("subtitle"),
                                "createdAt": composer.get("createdAt"),
                                "lastUpdatedAt": composer.get("lastUpdatedAt"),
                                "unifiedMode": composer.get("unifiedMode"),
                                "forceMode": composer.get("forceMode"),
                            }

        return workspace_map, composer_to_workspace, composer_heads

    def ingest_all(
        self, progress_callback: Optional[callable] = None, incremental: bool = False
    ) -> Dict[str, int]:
        """
        Ingest chats from Cursor databases.

        Parameters
        ----
        progress_callback : callable, optional
            Callback function(composer_id, total, current) for progress updates
        incremental : bool
            If True, only process chats updated since last run. If False, process all.

        Returns
        ----
        Dict[str, int]
            Statistics: {"ingested": count, "skipped": count, "errors": count}
        """
        source = "cursor"
        start_time = datetime.now()

        last_timestamp = None
        state = None

        if incremental:
            logger.info("Starting incremental chat ingestion from Cursor databases...")
            # Get last run state
            state = self.db.get_ingestion_state(source)
            if state and state.get("last_processed_timestamp"):
                try:
                    last_timestamp = datetime.fromisoformat(
                        state["last_processed_timestamp"]
                    )
                    logger.info("Last ingestion: %s", last_timestamp)
                    logger.info("Only processing chats updated since last run...")
                except (ValueError, TypeError):
                    logger.warning(
                        "Invalid last_processed_timestamp, falling back to full ingestion"
                    )
                    incremental = False
                    last_timestamp = None
            else:
                logger.info("No previous ingestion found, performing full ingestion...")
                incremental = False
                last_timestamp = None
        else:
            logger.info("Starting full chat ingestion from Cursor databases...")

        # Load workspace data once and build all mappings
        logger.info("Loading workspace data...")
        workspace_map, composer_to_workspace, composer_heads = (
            self._load_workspace_data()
        )
        logger.info(
            "Loaded %d workspaces, %d composer mappings",
            len(workspace_map),
            len(composer_to_workspace),
        )

        # Cache for inferred workspaces (path -> workspace_id)
        # Avoids repeated workspace creation for same inferred path
        inferred_workspace_cache: Dict[str, int] = {}
        stats_inferred = 0

        # Stream composers from global database (don't materialize)
        logger.info("Streaming composers from global database...")
        stats = {
            "ingested": 0,
            "skipped": 0,
            "errors": 0,
            "inferred_workspaces": 0,
            "updated": 0,
            "new": 0,
        }

        # Track last processed timestamp for incremental updates
        last_processed_timestamp = None
        last_composer_id = None

        # Get approximate total for progress (optional, can skip if slow)
        try:
            import sqlite3

            conn = sqlite3.connect(str(self.global_reader.db_path))
            cursor = conn.cursor()
            # Use range query with index for fast count
            cursor.execute(
                "SELECT COUNT(*) FROM cursorDiskKV WHERE key >= ? AND key < ?",
                ("composerData:", "composerData;"),
            )
            total = cursor.fetchone()[0]
            conn.close()
            logger.info("Found approximately %d composers to process", total)
        except Exception as e:
            logger.warning("Could not get total count: %s", e)
            total = None

        # Stream processing
        idx = 0
        processed_count = 0

        for composer_info in self.global_reader.read_all_composers():
            idx += 1
            composer_id = composer_info["composer_id"]
            composer_data = composer_info["data"]

            # Incremental mode: skip if chat hasn't been updated
            if incremental and state:
                # Check if this chat was updated since last run
                chat_updated_at = None
                if composer_data.get("lastUpdatedAt"):
                    try:
                        chat_updated_at = datetime.fromtimestamp(
                            composer_data["lastUpdatedAt"] / 1000
                        )
                    except (ValueError, TypeError):
                        pass

                # Also check composer head for lastUpdatedAt
                composer_head = composer_heads.get(composer_id)
                if (
                    not chat_updated_at
                    and composer_head
                    and composer_head.get("lastUpdatedAt")
                ):
                    try:
                        chat_updated_at = datetime.fromtimestamp(
                            composer_head["lastUpdatedAt"] / 1000
                        )
                    except (ValueError, TypeError):
                        pass

                # If we have a timestamp, check if it's newer than last run
                if chat_updated_at and last_timestamp:
                    if chat_updated_at <= last_timestamp:
                        # Timestamp suggests no update, but also check bubble count
                        # (Cursor sometimes doesn't update lastUpdatedAt when bubbles are added)
                        source_bubble_count = len(
                            composer_data.get("fullConversationHeadersOnly", [])
                        )
                        if source_bubble_count > 0:
                            # Check if database has fewer messages than source
                            cursor = self.db.conn.cursor()
                            cursor.execute(
                                "SELECT messages_count FROM chats WHERE cursor_composer_id = ?",
                                (composer_id,),
                            )
                            existing = cursor.fetchone()
                            if existing:
                                db_message_count = existing[0] or 0
                                if source_bubble_count > db_message_count:
                                    # New bubbles added but timestamp not updated
                                    # Force re-ingestion
                                    logger.debug(
                                        "Composer %s has new bubbles (%d > %d) despite old timestamp, re-ingesting",
                                        composer_id,
                                        source_bubble_count,
                                        db_message_count,
                                    )
                                    pass  # Continue to processing
                                else:
                                    # Chat hasn't been updated since last run - skip it
                                    stats["skipped"] += 1
                                    continue
                            else:
                                # Chat not in database yet - process it
                                pass
                        else:
                            # No bubbles in source - skip it
                            stats["skipped"] += 1
                            continue
                    # Chat has been updated - process it
                elif not chat_updated_at:
                    # No timestamp available in source - check database for existing chat
                    cursor = self.db.conn.cursor()
                    cursor.execute(
                        "SELECT id, last_updated_at FROM chats WHERE cursor_composer_id = ?",
                        (composer_id,),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        # Chat exists in database - use its stored timestamp for comparison
                        db_last_updated = existing[1]  # last_updated_at column
                        if db_last_updated:
                            try:
                                db_timestamp = datetime.fromisoformat(db_last_updated)
                                # If database timestamp is older than last run, skip it
                                # (we already ingested it in a previous run)
                                if last_timestamp and db_timestamp <= last_timestamp:
                                    stats["skipped"] += 1
                                    continue
                            except (ValueError, TypeError):
                                # Invalid timestamp format - fall through to process
                                pass
                        # If no database timestamp or can't parse, skip it anyway
                        # (assume unchanged since we have no evidence it changed)
                        stats["skipped"] += 1
                        continue
                    # Chat doesn't exist in database - process it (it's new)

            if progress_callback and total:
                progress_callback(composer_id, total, idx)

            try:
                # Find workspace for this composer
                workspace_id = composer_to_workspace.get(composer_id)

                # If no workspace found, try inference from file context
                if workspace_id is None:
                    inferred_path = self._infer_workspace_from_context(composer_data)
                    if inferred_path:
                        # Check cache first
                        if inferred_path in inferred_workspace_cache:
                            workspace_id = inferred_workspace_cache[inferred_path]
                        else:
                            # Create workspace from inferred path
                            # Extract path from file:// URI
                            workspace_path = inferred_path
                            if workspace_path.startswith("file://"):
                                workspace_path = workspace_path[7:]

                            workspace = Workspace(
                                workspace_hash="",  # No hash for inferred workspaces
                                folder_uri=inferred_path,
                                resolved_path=workspace_path,
                            )
                            workspace_id = self.db.upsert_workspace(workspace)
                            inferred_workspace_cache[inferred_path] = workspace_id
                            stats["inferred_workspaces"] += 1
                            stats_inferred += 1

                            if stats_inferred % 10 == 0:
                                logger.debug(
                                    "Inferred %d workspaces from file context",
                                    stats_inferred,
                                )

                # Get composer head for title enrichment
                composer_head_dict = composer_heads.get(composer_id)

                # Convert to domain model
                chat = self._convert_composer_to_chat(
                    composer_data, workspace_id, composer_head_dict
                )
                if not chat:
                    stats["skipped"] += 1
                    continue

                # Skip empty chats (no messages)
                if not chat.messages:
                    stats["skipped"] += 1
                    continue

                # Store in database
                # Check if this is actually an update or a new chat
                cursor = self.db.conn.cursor()
                cursor.execute(
                    "SELECT id FROM chats WHERE cursor_composer_id = ?",
                    (chat.cursor_composer_id,),
                )
                existing_chat = cursor.fetchone()
                is_new = existing_chat is None

                self.db.upsert_chat(chat)

                if is_new:
                    stats["ingested"] += 1
                    stats["new"] += 1
                else:
                    stats["ingested"] += 1
                    stats["updated"] += 1

                processed_count += 1

                # Track last processed timestamp
                if chat.last_updated_at:
                    if (
                        not last_processed_timestamp
                        or chat.last_updated_at > last_processed_timestamp
                    ):
                        last_processed_timestamp = chat.last_updated_at
                        last_composer_id = composer_id
                elif chat.created_at:
                    if (
                        not last_processed_timestamp
                        or chat.created_at > last_processed_timestamp
                    ):
                        last_processed_timestamp = chat.created_at
                        last_composer_id = composer_id

                if processed_count % 100 == 0:
                    logger.info("Processed %d composers...", processed_count)

            except Exception as e:
                logger.error("Error processing composer %s: %s", composer_id, e)
                stats["errors"] += 1

        # Update ingestion state
        self.db.update_ingestion_state(
            source=source,
            last_run_at=start_time,
            last_processed_timestamp=last_processed_timestamp.isoformat()
            if last_processed_timestamp
            else None,
            last_composer_id=last_composer_id,
            stats=stats,
        )

        if incremental:
            logger.info(
                "Incremental ingestion complete: %d ingested (%d new, %d updated), %d skipped, %d errors, %d workspaces inferred",
                stats["ingested"],
                stats.get("new", 0),
                stats.get("updated", 0),
                stats["skipped"],
                stats["errors"],
                stats["inferred_workspaces"],
            )
        else:
            logger.info(
                "Ingestion complete: %d ingested, %d skipped, %d errors, %d workspaces inferred",
                stats["ingested"],
                stats["skipped"],
                stats["errors"],
                stats["inferred_workspaces"],
            )

        # Ingest plans after chats are ingested (plans link to chats)
        logger.info("Ingesting plans...")
        plan_stats = self.ingest_plans()
        logger.info(
            "Plan ingestion complete: %d plans ingested", plan_stats.get("ingested", 0)
        )

        return stats

    def _link_composers_to_plan(
        self,
        plan_id: int,
        plan_identifier: str,
        composer_ids: List[str],
        relationship: str,
    ) -> None:
        """
        Link multiple composer IDs to a plan with a given relationship.

        Parameters
        ----
        plan_id : int
            Plan database ID
        plan_identifier : str
            Plan identifier for logging (e.g., "complete_chatrxiv_migration_f77a44d3")
        composer_ids : List[str]
            List of composer IDs to link
        relationship : str
            Relationship type: 'created', 'edited', or 'referenced'
        """
        for composer_id in composer_ids:
            if not composer_id:
                continue
            chat = self.db.get_chat_by_composer_id(composer_id)
            if chat:
                self.db.link_chat_to_plan(
                    chat_id=chat["id"],
                    plan_id=plan_id,
                    relationship=relationship,
                )
            else:
                logger.debug(
                    "Plan %s references non-existent chat composer_id (%s): %s",
                    plan_identifier,
                    relationship,
                    composer_id,
                )

    def ingest_plans(self) -> Dict[str, int]:
        """
        Ingest plans from Cursor's plan registry.

        Reads plan metadata from composer.planRegistry and links plans to chats
        based on createdBy, editedBy, and referencedBy relationships.

        Note: This method only adds relationships; it does not remove relationships
        that no longer exist in Cursor's registry. This is intentional to avoid
        accidentally removing valid relationships due to timing issues or registry
        inconsistencies. If cleanup is needed, it can be added later.

        Returns
        ----
        Dict[str, int]
            Statistics: {"ingested": count, "errors": count}
        """
        stats = {"ingested": 0, "errors": 0}

        try:
            # Get plan metadata from registry
            plans = self.plan_reader.get_plan_metadata()

            for plan_data in plans:
                try:
                    # Upsert plan
                    plan_db_id = self.db.upsert_plan(
                        plan_id=plan_data["plan_id"],
                        name=plan_data["name"],
                        file_path=plan_data["file_path"],
                        created_at=plan_data["created_at"],
                        last_updated_at=plan_data["last_updated_at"],
                    )

                    # Link chats to plan based on relationships
                    if plan_data["created_by"]:
                        self._link_composers_to_plan(
                            plan_id=plan_db_id,
                            plan_identifier=plan_data["plan_id"],
                            composer_ids=[plan_data["created_by"]],
                            relationship="created",
                        )

                    self._link_composers_to_plan(
                        plan_id=plan_db_id,
                        plan_identifier=plan_data["plan_id"],
                        composer_ids=plan_data.get("edited_by", []),
                        relationship="edited",
                    )

                    self._link_composers_to_plan(
                        plan_id=plan_db_id,
                        plan_identifier=plan_data["plan_id"],
                        composer_ids=plan_data.get("referenced_by", []),
                        relationship="referenced",
                    )

                    stats["ingested"] += 1

                except Exception as e:
                    logger.error(
                        "Error ingesting plan %s: %s", plan_data.get("plan_id"), e
                    )
                    stats["errors"] += 1

        except Exception as e:
            logger.error("Error reading plan registry: %s", e)
            stats["errors"] += 1

        return stats

    def _convert_claude_to_chat(
        self, conversation_data: Dict[str, Any]
    ) -> Optional[Chat]:
        """
        Convert Claude.ai conversation data to Chat domain model.

        Parameters
        ----
        conversation_data : Dict[str, Any]
            Raw conversation data from Claude.ai API

        Returns
        ----
        Chat
            Chat domain model, or None if conversion fails
        """
        conv_id = conversation_data.get("uuid")
        if not conv_id:
            return None

        # Extract title
        title = (
            conversation_data.get("name")
            or conversation_data.get("summary")
            or "Untitled Chat"
        )

        # Extract timestamps
        created_at = None
        if conversation_data.get("created_at"):
            try:
                # Parse ISO format timestamp
                created_at_str = conversation_data["created_at"]
                if created_at_str.endswith("Z"):
                    created_at_str = created_at_str[:-1] + "+00:00"
                created_at = datetime.fromisoformat(created_at_str)
            except (ValueError, TypeError) as e:
                logger.debug("Could not parse created_at: %s", e)

        last_updated_at = None
        if conversation_data.get("updated_at"):
            try:
                updated_at_str = conversation_data["updated_at"]
                if updated_at_str.endswith("Z"):
                    updated_at_str = updated_at_str[:-1] + "+00:00"
                last_updated_at = datetime.fromisoformat(updated_at_str)
            except (ValueError, TypeError) as e:
                logger.debug("Could not parse updated_at: %s", e)

        # Extract messages
        messages = []
        chat_messages = conversation_data.get("chat_messages", [])

        for msg_data in chat_messages:
            # Map sender to role
            sender = msg_data.get("sender", "")
            if sender == "human":
                role = MessageRole.USER
            elif sender == "assistant":
                role = MessageRole.ASSISTANT
            else:
                # Skip unknown sender types
                continue

            # Extract text content
            text = ""
            rich_text = ""
            content = msg_data.get("content", [])

            # Claude stores content as array of content blocks
            for content_block in content:
                if content_block.get("type") == "text":
                    block_text = content_block.get("text", "")
                    if block_text:
                        if text:
                            text += "\n\n" + block_text
                        else:
                            text = block_text

            # If no text content, check for other content types
            if not text:
                # Check if there's a text field directly on the message
                text = msg_data.get("text", "")

            # Extract timestamp
            msg_created_at = None
            if msg_data.get("created_at"):
                try:
                    created_at_str = msg_data["created_at"]
                    if created_at_str.endswith("Z"):
                        created_at_str = created_at_str[:-1] + "+00:00"
                    msg_created_at = datetime.fromisoformat(created_at_str)
                except (ValueError, TypeError):
                    pass

            # Classify message type
            message_type = MessageType.RESPONSE if text else MessageType.EMPTY

            message = Message(
                role=role,
                text=text,
                rich_text=rich_text,
                created_at=msg_created_at or created_at,
                cursor_bubble_id=msg_data.get("uuid"),
                raw_json=msg_data,
                message_type=message_type,
            )
            messages.append(message)

        # Extract model (store in mode field for now, could add separate field later)
        model = conversation_data.get("model")
        mode = ChatMode.CHAT  # Claude conversations are always chat mode

        # Create chat
        chat = Chat(
            cursor_composer_id=conv_id,  # Reuse this field for Claude conversation ID
            workspace_id=None,  # Claude conversations don't have workspaces
            title=title,
            mode=mode,
            created_at=created_at,
            last_updated_at=last_updated_at,
            source="claude.ai",
            messages=messages,
            relevant_files=[],  # Claude API doesn't expose relevant files in this format
        )

        return chat

    def _parse_claude_timestamp(
        self, timestamp_str: Optional[str]
    ) -> Optional[datetime]:
        """
        Parse Claude.ai timestamp string to datetime.

        Parameters
        ----
        timestamp_str : str, optional
            ISO format timestamp string (may end with 'Z')

        Returns
        ----
        datetime, optional
            Parsed datetime or None if parsing fails
        """
        if not timestamp_str:
            return None
        try:
            if timestamp_str.endswith("Z"):
                timestamp_str = timestamp_str[:-1] + "+00:00"
            return datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            return None

    def _ingest_web_source(
        self,
        config: WebSourceConfig,
        progress_callback: Optional[Callable] = None,
        incremental: bool = False,
    ) -> Dict[str, int]:
        """
        Generic ingestion for web-based conversation sources.

        Template method that handles common ingestion flow:
        1. Initialize reader
        2. Fetch conversation list
        3. Filter for incremental (if enabled)
        4. Fetch details and convert
        5. Store in database

        Parameters
        ----
        config : WebSourceConfig
            Source-specific configuration
        progress_callback : Callable, optional
            Progress callback(conv_id, total, current)
        incremental : bool
            Only fetch new/updated conversations

        Returns
        ----
        Dict[str, int]
            Statistics: {ingested, skipped, errors}
        """
        logger.info(
            "Starting %s chat ingestion%s...",
            config.name,
            " (incremental)" if incremental else "",
        )

        try:
            reader = config.reader_class()
        except ValueError as e:
            logger.error(
                "%s reader initialization failed: %s", config.name.capitalize(), e
            )
            if config.name == "claude":
                logger.error("Please configure CLAUDE_ORG_ID and CLAUDE_SESSION_COOKIE")
            elif config.name == "chatgpt":
                logger.error("Please configure CHATGPT_SESSION_TOKEN")
            return {"ingested": 0, "skipped": 0, "errors": 1}

        stats = {"ingested": 0, "skipped": 0, "errors": 0}

        try:
            # Step 1: Get conversation list
            conversation_list = reader.get_conversation_list()
            logger.info(
                "Found %d %s conversations", len(conversation_list), config.name
            )

            # Step 2: Filter if incremental
            conversations_to_fetch = []
            if incremental:
                for conv_meta in conversation_list:
                    conv_id = conv_meta.get(config.id_field)
                    if not conv_id:
                        continue

                    api_updated_at = config.timestamp_parser(
                        conv_meta.get(config.updated_field)
                    )

                    # Check if we have this conversation and when it was last updated
                    db_chat = self.db.get_chat_by_composer_id(conv_id)

                    if db_chat is None:
                        # New conversation
                        conversations_to_fetch.append(conv_meta)
                    elif api_updated_at and db_chat.get("last_updated_at"):
                        db_updated_at = datetime.fromisoformat(
                            db_chat["last_updated_at"]
                        )
                        if api_updated_at > db_updated_at:
                            # Updated since we last stored it
                            conversations_to_fetch.append(conv_meta)
                        else:
                            stats["skipped"] += 1
                    else:
                        # Can't compare timestamps, fetch to be safe
                        conversations_to_fetch.append(conv_meta)

                logger.info(
                    "Incremental: %d new/updated, %d unchanged",
                    len(conversations_to_fetch),
                    stats["skipped"],
                )
            else:
                conversations_to_fetch = conversation_list

            total = len(conversations_to_fetch)
            logger.info("Processing %d conversations...", total)

            # Step 3: Fetch details only for filtered conversations
            for idx, conv_meta in enumerate(conversations_to_fetch, 1):
                conv_id = conv_meta.get(config.id_field, f"unknown-{idx}")

                if progress_callback and total:
                    progress_callback(conv_id, total, idx)

                try:
                    # Fetch full conversation details
                    full_conv = reader._fetch_conversation_detail(conv_id)
                    if not full_conv:
                        stats["skipped"] += 1
                        continue

                    # Merge metadata with full details
                    full_conv.update(conv_meta)

                    # Convert to domain model
                    chat = config.converter(full_conv)
                    if not chat:
                        stats["skipped"] += 1
                        continue

                    # Skip empty chats (no messages)
                    if not chat.messages:
                        stats["skipped"] += 1
                        continue

                    # Store in database
                    self.db.upsert_chat(chat)
                    stats["ingested"] += 1

                    if idx % 50 == 0:
                        logger.info(
                            "Processed %d/%d %s conversations...",
                            idx,
                            total,
                            config.name,
                        )

                except Exception as e:
                    logger.error(
                        "Error processing %s conversation %s: %s",
                        config.name,
                        conv_id,
                        e,
                    )
                    stats["errors"] += 1

            logger.info(
                "%s ingestion complete: %d ingested, %d skipped, %d errors",
                config.name.capitalize(),
                stats["ingested"],
                stats["skipped"],
                stats["errors"],
            )

        except Exception as e:
            logger.error("Error during %s ingestion: %s", config.name, e)
            stats["errors"] += 1

        return stats

    def ingest_claude(
        self, progress_callback: Optional[callable] = None, incremental: bool = False
    ) -> Dict[str, int]:
        """
        Ingest chats from Claude.ai.

        Parameters
        ----
        progress_callback : callable, optional
            Callback function(conversation_id, total, current) for progress updates
        incremental : bool
            If True, only fetch details for conversations that are new or updated

        Returns
        ----
        Dict[str, int]
            Statistics: {"ingested": count, "skipped": count, "errors": count}
        """
        config = WebSourceConfig(
            name="claude",
            reader_class=ClaudeReader,
            id_field="uuid",
            updated_field="updated_at",
            converter=self._convert_claude_to_chat,
            timestamp_parser=self._parse_claude_timestamp,
        )
        return self._ingest_web_source(config, progress_callback, incremental)

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

    def _convert_chatgpt_to_chat(
        self, conversation_data: Dict[str, Any]
    ) -> Optional[Chat]:
        """
        Convert ChatGPT conversation data to Chat domain model.

        Key differences from Claude:
        - Uses "id" instead of "uuid"
        - Timestamps can be Unix epoch or ISO strings
        - Messages already flattened by ChatGPTReader
        - Sender is "user"/"assistant" vs "human"/"assistant"

        Parameters
        ----
        conversation_data : Dict[str, Any]
            Raw conversation from ChatGPT API (includes chat_messages from reader)

        Returns
        ----
        Chat or None
            Chat domain model, or None if conversion fails
        """
        conv_id = conversation_data.get("id")
        if not conv_id:
            return None

        # Extract title
        title = conversation_data.get("title", "Untitled Chat")

        # Extract timestamps (ChatGPT uses both Unix epoch and ISO strings)
        created_at = None
        create_time = conversation_data.get("create_time")
        if create_time:
            created_at = self._parse_chatgpt_timestamp(create_time)

        last_updated_at = None
        update_time = conversation_data.get("update_time")
        if update_time:
            last_updated_at = self._parse_chatgpt_timestamp(update_time)

        # Extract messages (already flattened by ChatGPTReader)
        messages = []
        chat_messages = conversation_data.get("chat_messages", [])

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

    def ingest_chatgpt(
        self, progress_callback: Optional[callable] = None, incremental: bool = False
    ) -> Dict[str, int]:
        """
        Ingest chats from ChatGPT.

        Parameters
        ----
        progress_callback : callable, optional
            Callback function(conversation_id, total, current) for progress updates
        incremental : bool
            If True, only fetch details for conversations that are new or updated

        Returns
        ----
        Dict[str, int]
            Statistics: {"ingested": count, "skipped": count, "errors": count}
        """
        config = WebSourceConfig(
            name="chatgpt",
            reader_class=ChatGPTReader,
            id_field="id",
            updated_field="update_time",
            converter=self._convert_chatgpt_to_chat,
            timestamp_parser=self._parse_chatgpt_timestamp,
        )
        return self._ingest_web_source(config, progress_callback, incremental)

    def _convert_claude_code_to_chat(
        self, session_data: Dict[str, Any]
    ) -> Optional[Chat]:
        """
        Convert Claude Code session data to Chat domain model.

        Parameters
        ----------
        session_data : Dict[str, Any]
            Session data from ClaudeCodeReader

        Returns
        -------
        Chat
            Chat domain model, or None if conversion fails
        """
        session_id = session_data.get("session_id")
        if not session_id:
            return None

        # Extract title from summary or metadata
        title = session_data.get("summary") or "Untitled Session"
        if title == "Untitled Session":
            # Try to extract from metadata slug
            metadata = session_data.get("metadata", {})
            slug = metadata.get("slug")
            if slug:
                title = slug.replace("-", " ").title()

        # Extract messages
        raw_messages = session_data.get("messages", [])
        messages = []
        model_used = None
        total_input_tokens = 0
        total_output_tokens = 0

        for msg_data in raw_messages:
            # Map role
            role_str = msg_data.get("role", "user")
            if role_str == "user":
                role = MessageRole.USER
            elif role_str == "assistant":
                role = MessageRole.ASSISTANT
            else:
                continue

            # Extract text content
            text = msg_data.get("content", "")

            # Extract thinking content if present
            thinking = msg_data.get("thinking")
            if thinking:
                text = f"[Thinking]\n{thinking}\n\n{text}" if text else f"[Thinking]\n{thinking}"

            # Extract tool calls if present
            tool_calls = msg_data.get("tool_calls")
            if tool_calls:
                tool_summary = []
                for tc in tool_calls:
                    tool_name = tc.get("name", "unknown")
                    tool_summary.append(f"[Tool: {tool_name}]")
                if tool_summary:
                    tool_text = "\n".join(tool_summary)
                    text = f"{text}\n\n{tool_text}" if text else tool_text

            # Parse timestamp
            msg_created_at = None
            timestamp_str = msg_data.get("timestamp")
            if timestamp_str:
                try:
                    if timestamp_str.endswith("Z"):
                        timestamp_str = timestamp_str[:-1] + "+00:00"
                    msg_created_at = datetime.fromisoformat(timestamp_str)
                except (ValueError, TypeError):
                    pass

            # Classify message type
            if msg_data.get("thinking"):
                message_type = MessageType.THINKING
            elif msg_data.get("tool_calls"):
                message_type = MessageType.TOOL_CALL
            elif text:
                message_type = MessageType.RESPONSE
            else:
                message_type = MessageType.EMPTY

            # Extract model and usage from assistant messages
            if role == MessageRole.ASSISTANT:
                if not model_used:
                    model_used = msg_data.get("model")
                usage = msg_data.get("usage", {})
                if usage:
                    total_input_tokens += usage.get("input_tokens", 0)
                    total_output_tokens += usage.get("output_tokens", 0)

            message = Message(
                role=role,
                text=text,
                rich_text="",
                created_at=msg_created_at,
                cursor_bubble_id=msg_data.get("uuid"),
                raw_json=msg_data,
                message_type=message_type,
            )
            messages.append(message)

        # Skip empty sessions
        if not messages:
            return None

        # Extract timestamps from first/last messages
        created_at = messages[0].created_at if messages else None
        last_updated_at = messages[-1].created_at if messages else None

        # Determine mode based on tool usage
        has_tool_calls = any(m.message_type == MessageType.TOOL_CALL for m in messages)
        mode = ChatMode.AGENT if has_tool_calls else ChatMode.CHAT

        # Calculate estimated cost (rough estimate based on Claude pricing)
        estimated_cost = None
        if total_input_tokens or total_output_tokens:
            # Use approximate pricing (varies by model)
            # Sonnet: $3/1M input, $15/1M output
            # Opus: $15/1M input, $75/1M output
            if model_used and "opus" in model_used.lower():
                estimated_cost = (total_input_tokens * 15 + total_output_tokens * 75) / 1_000_000
            else:
                estimated_cost = (total_input_tokens * 3 + total_output_tokens * 15) / 1_000_000

        # Create chat
        chat = Chat(
            cursor_composer_id=session_id,
            workspace_id=None,  # Could be inferred from project_path later
            title=title,
            mode=mode,
            created_at=created_at,
            last_updated_at=last_updated_at,
            source="claude-code",
            summary=session_data.get("summary"),
            model=model_used,
            estimated_cost=estimated_cost,
            messages=messages,
            relevant_files=[],  # Could extract from tool calls later
        )

        return chat

    def ingest_claude_code(
        self, progress_callback: Optional[Callable] = None, incremental: bool = False
    ) -> Dict[str, int]:
        """
        Ingest chats from Claude Code local storage.

        Parameters
        ----------
        progress_callback : callable, optional
            Callback function(session_id, total, current) for progress updates
        incremental : bool
            If True, only process sessions updated since last run

        Returns
        -------
        Dict[str, int]
            Statistics: {"ingested": count, "skipped": count, "errors": count}
        """
        source = "claude-code"
        start_time = datetime.now()

        logger.info(
            "Starting Claude Code chat ingestion%s...",
            " (incremental)" if incremental else "",
        )

        reader = ClaudeCodeReader()
        stats = {"ingested": 0, "skipped": 0, "errors": 0, "subagents": 0}

        # Check for incremental state
        last_timestamp = None
        if incremental:
            state = self.db.get_ingestion_state(source)
            if state and state.get("last_processed_timestamp"):
                try:
                    last_timestamp = datetime.fromisoformat(
                        state["last_processed_timestamp"]
                    )
                    logger.info("Last ingestion: %s", last_timestamp)
                except (ValueError, TypeError):
                    pass

        try:
            # Stream sessions from all projects
            sessions = list(reader.read_all_sessions())
            total = len(sessions)
            logger.info("Found %d Claude Code sessions", total)

            last_processed_timestamp = None
            last_session_id = None

            for idx, session_data in enumerate(sessions, 1):
                session_id = session_data.get("session_id", f"unknown-{idx}")

                if progress_callback and total:
                    progress_callback(session_id, total, idx)

                try:
                    # Get session timestamp for incremental check
                    session_messages = session_data.get("messages", [])
                    if session_messages:
                        last_msg_ts_str = session_messages[-1].get("timestamp")
                        if last_msg_ts_str:
                            try:
                                if last_msg_ts_str.endswith("Z"):
                                    last_msg_ts_str = last_msg_ts_str[:-1] + "+00:00"
                                session_last_updated = datetime.fromisoformat(last_msg_ts_str)

                                # Incremental: skip if not updated
                                if incremental and last_timestamp:
                                    if session_last_updated <= last_timestamp:
                                        stats["skipped"] += 1
                                        continue
                            except (ValueError, TypeError):
                                pass

                    # Convert to domain model
                    chat = self._convert_claude_code_to_chat(session_data)
                    if not chat:
                        stats["skipped"] += 1
                        continue

                    # Store in database
                    self.db.upsert_chat(chat)
                    stats["ingested"] += 1

                    # Track last processed timestamp
                    if chat.last_updated_at:
                        if not last_processed_timestamp or chat.last_updated_at > last_processed_timestamp:
                            last_processed_timestamp = chat.last_updated_at
                            last_session_id = session_id

                    # Process subagents if present
                    subagents = session_data.get("subagents", [])
                    for subagent_data in subagents:
                        try:
                            subagent_chat = self._convert_claude_code_to_chat(subagent_data)
                            if subagent_chat:
                                # Prefix subagent title with parent session
                                subagent_chat.title = f"[Subagent] {subagent_chat.title}"
                                self.db.upsert_chat(subagent_chat)
                                stats["subagents"] += 1
                        except Exception as e:
                            logger.debug("Error processing subagent: %s", e)

                    if idx % 50 == 0:
                        logger.info("Processed %d/%d Claude Code sessions...", idx, total)

                except Exception as e:
                    logger.error("Error processing session %s: %s", session_id, e)
                    stats["errors"] += 1

            # Update ingestion state
            self.db.update_ingestion_state(
                source=source,
                last_run_at=start_time,
                last_processed_timestamp=last_processed_timestamp.isoformat()
                if last_processed_timestamp
                else None,
                last_composer_id=last_session_id,
                stats=stats,
            )

            logger.info(
                "Claude Code ingestion complete: %d ingested, %d subagents, %d skipped, %d errors",
                stats["ingested"],
                stats["subagents"],
                stats["skipped"],
                stats["errors"],
            )

        except Exception as e:
            logger.error("Error during Claude Code ingestion: %s", e)
            stats["errors"] += 1

        return stats
