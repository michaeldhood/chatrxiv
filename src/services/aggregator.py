"""
Chat aggregator service.

Orchestrates extraction from Cursor databases, linking workspace metadata
to global composer conversations, and storing normalized data.
"""
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime

from src.core.db import ChatDatabase
from src.core.models import Chat, Message, Workspace, ChatMode, MessageRole, MessageType
from src.readers.workspace_reader import WorkspaceStateReader
from src.readers.global_reader import GlobalComposerReader
from src.readers.claude_reader import ClaudeReader

logger = logging.getLogger(__name__)


class ChatAggregator:
    """
    Aggregates chats from Cursor databases into normalized local database.
    
    Handles:
    - Reading workspace metadata
    - Reading global composer conversations
    - Linking composers to workspaces
    - Converting to domain models
    - Storing in local database
    """
    
    def __init__(self, db: ChatDatabase):
        """
        Initialize aggregator.
        
        Parameters
        ----
        db : ChatDatabase
            Database instance for storing aggregated data
        """
        self.db = db
        self.workspace_reader = WorkspaceStateReader()
        self.global_reader = GlobalComposerReader()
    
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
        bubble_ids = [header.get("bubbleId") for header in headers if header.get("bubbleId")]
        
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
        if (bubble.get("codeBlock") or 
            bubble.get("toolFormerResult") or
            bubble.get("toolCalls") or
            bubble.get("toolCall")):
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
                    if (current / "package.json").exists() or \
                       (current / "pyproject.toml").exists() or \
                       (current / "setup.py").exists() or \
                       (current / "Cargo.toml").exists() or \
                       (current / "go.mod").exists():
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
                    if current.name and current.name not in ["sources", "src", "lib", "dlt"]:
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
            return uri.get("fsPath") or uri.get("path") or uri.get("external", "").replace("file://", "")
        elif isinstance(uri, str):
            if uri.startswith("file://"):
                return uri[7:]  # Remove "file://" prefix
            return uri
        return None
    
    def _infer_workspace_from_context(self, composer_data: Dict[str, Any]) -> Optional[str]:
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
            clean_path = path.replace("file://", "") if path.startswith("file://") else path
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
    
    def _convert_composer_to_chat(self, composer_data: Dict[str, Any], 
                                   workspace_id: Optional[int] = None,
                                   composer_head: Optional[Dict[str, Any]] = None) -> Optional[Chat]:
        """
        Convert Cursor composer data to Chat domain model.
        
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
        composer_id = composer_data.get("composerId")
        if not composer_id:
            return None
        
        # Determine mode (prefer workspace head, then global data)
        force_mode = None
        unified_mode = None
        
        if composer_head:
            force_mode = composer_head.get("forceMode")
            unified_mode = composer_head.get("unifiedMode")
        
        if not force_mode:
            force_mode = composer_data.get("forceMode", "chat")
        if not unified_mode:
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
        if composer_head:
            title = composer_head.get("name") or composer_head.get("subtitle")
        
        if not title:
            title = composer_data.get("name") or composer_data.get("subtitle")
        
        if not title:
            title = "Untitled Chat"
        
        # Extract timestamps (prefer workspace head, then global data)
        created_at = None
        if composer_head and composer_head.get("createdAt"):
            try:
                created_at = datetime.fromtimestamp(composer_head["createdAt"] / 1000)
            except (ValueError, TypeError):
                pass
        
        if not created_at and composer_data.get("createdAt"):
            try:
                created_at = datetime.fromtimestamp(composer_data["createdAt"] / 1000)
            except (ValueError, TypeError):
                pass
        
        last_updated_at = None
        if composer_head and composer_head.get("lastUpdatedAt"):
            try:
                last_updated_at = datetime.fromtimestamp(composer_head["lastUpdatedAt"] / 1000)
            except (ValueError, TypeError):
                pass
        
        if not last_updated_at and composer_data.get("lastUpdatedAt"):
            try:
                last_updated_at = datetime.fromtimestamp(composer_data["lastUpdatedAt"] / 1000)
            except (ValueError, TypeError):
                pass
        
        # Extract conversation - try multiple formats
        # Format 1: Old style with full conversation array
        conversation = composer_data.get("conversation", [])
        
        # Format 2: New style with headers-only + separate bubble storage
        # If conversation is empty, try fullConversationHeadersOnly
        if not conversation:
            headers = composer_data.get("fullConversationHeadersOnly", [])
            if headers:
                conversation = self._resolve_conversation_from_headers(
                    composer_id, headers
                )
        
        messages = []
        relevant_files = set()
        detected_models = set()  # Track all models used in this chat
        
        for bubble in conversation:
            bubble_type = bubble.get("type")
            if bubble_type == 1:  # User message
                role = MessageRole.USER
            elif bubble_type == 2:  # AI response
                role = MessageRole.ASSISTANT
                # Extract model information from AI responses
                model = bubble.get("modelType") or bubble.get("model")
                if model:
                    detected_models.add(model)
            else:
                continue  # Skip unknown types
            
            text = bubble.get("text", "")
            rich_text = bubble.get("richText", "")
            
            # Classify the bubble type
            message_type = self._classify_bubble(bubble)
            
            # Extract timestamp
            msg_created_at = None
            if bubble.get("createdAt"):
                try:
                    msg_created_at = datetime.fromtimestamp(bubble["createdAt"] / 1000)
                except (ValueError, TypeError):
                    pass
            
            message = Message(
                role=role,
                text=text,
                rich_text=rich_text,
                created_at=msg_created_at or created_at,  # Fallback to chat created_at
                cursor_bubble_id=bubble.get("bubbleId"),
                raw_json=bubble,
                message_type=message_type,
            )
            messages.append(message)
            
            # Extract relevant files
            for file_path in bubble.get("relevantFiles", []):
                relevant_files.add(file_path)
        
        # Determine primary model (use most common, or first if all equal)
        primary_model = None
        if detected_models:
            # Use the first detected model (most recent conversations tend to use consistent models)
            primary_model = list(detected_models)[0]
        
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
            model=primary_model,
        )
        
        return chat
    
    def _load_workspace_data(self) -> Tuple[Dict[str, int], Dict[str, Optional[int]], Dict[str, Dict[str, Any]]]:
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
            workspace = Workspace(
                workspace_hash=workspace_hash,
                folder_uri=metadata.get("project_path", ""),
                resolved_path=metadata.get("project_path", ""),
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
                        
                        # Build composer_heads map
                        composer_heads[composer_id] = {
                            "name": composer.get("name"),
                            "subtitle": composer.get("subtitle"),
                            "createdAt": composer.get("createdAt"),
                            "lastUpdatedAt": composer.get("lastUpdatedAt"),
                            "unifiedMode": composer.get("unifiedMode"),
                            "forceMode": composer.get("forceMode"),
                        }
        
        return workspace_map, composer_to_workspace, composer_heads
    
    def ingest_all(self, progress_callback: Optional[callable] = None, 
                   incremental: bool = False) -> Dict[str, int]:
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
                    last_timestamp = datetime.fromisoformat(state["last_processed_timestamp"])
                    logger.info("Last ingestion: %s", last_timestamp)
                    logger.info("Only processing chats updated since last run...")
                except (ValueError, TypeError):
                    logger.warning("Invalid last_processed_timestamp, falling back to full ingestion")
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
        workspace_map, composer_to_workspace, composer_heads = self._load_workspace_data()
        logger.info("Loaded %d workspaces, %d composer mappings", 
                   len(workspace_map), len(composer_to_workspace))
        
        # Cache for inferred workspaces (path -> workspace_id)
        # Avoids repeated workspace creation for same inferred path
        inferred_workspace_cache: Dict[str, int] = {}
        stats_inferred = 0
        
        # Stream composers from global database (don't materialize)
        logger.info("Streaming composers from global database...")
        stats = {"ingested": 0, "skipped": 0, "errors": 0, "inferred_workspaces": 0, "updated": 0, "new": 0}
        
        # Track last processed timestamp for incremental updates
        last_processed_timestamp = None
        last_composer_id = None
        
        # Get approximate total for progress (optional, can skip if slow)
        try:
            import sqlite3
            conn = sqlite3.connect(str(self.global_reader.db_path))
            cursor = conn.cursor()
            # Use range query with index for fast count
            cursor.execute("SELECT COUNT(*) FROM cursorDiskKV WHERE key >= ? AND key < ?", 
                         ("composerData:", "composerData;"))
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
                        chat_updated_at = datetime.fromtimestamp(composer_data["lastUpdatedAt"] / 1000)
                    except (ValueError, TypeError):
                        pass
                
                # Also check composer head for lastUpdatedAt
                composer_head = composer_heads.get(composer_id)
                if not chat_updated_at and composer_head and composer_head.get("lastUpdatedAt"):
                    try:
                        chat_updated_at = datetime.fromtimestamp(composer_head["lastUpdatedAt"] / 1000)
                    except (ValueError, TypeError):
                        pass
                
                # If we have a timestamp, check if it's newer than last run
                if chat_updated_at and last_timestamp:
                    if chat_updated_at <= last_timestamp:
                        # Chat hasn't been updated since last run - skip it
                        stats["skipped"] += 1
                        continue
                    # Chat has been updated - process it
                elif not chat_updated_at:
                    # No timestamp available in source - check database for existing chat
                    cursor = self.db.conn.cursor()
                    cursor.execute("SELECT id, last_updated_at FROM chats WHERE cursor_composer_id = ?", 
                                 (composer_id,))
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
                                logger.debug("Inferred %d workspaces from file context", stats_inferred)
                
                # Get composer head for title enrichment
                composer_head = composer_heads.get(composer_id)
                
                # Convert to domain model
                chat = self._convert_composer_to_chat(composer_data, workspace_id, composer_head)
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
                cursor.execute("SELECT id FROM chats WHERE cursor_composer_id = ?", (chat.cursor_composer_id,))
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
                    if not last_processed_timestamp or chat.last_updated_at > last_processed_timestamp:
                        last_processed_timestamp = chat.last_updated_at
                        last_composer_id = composer_id
                elif chat.created_at:
                    if not last_processed_timestamp or chat.created_at > last_processed_timestamp:
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
            last_processed_timestamp=last_processed_timestamp.isoformat() if last_processed_timestamp else None,
            last_composer_id=last_composer_id,
            stats=stats
        )
        
        if incremental:
            logger.info("Incremental ingestion complete: %d ingested (%d new, %d updated), %d skipped, %d errors, %d workspaces inferred", 
                       stats["ingested"], stats.get("new", 0), stats.get("updated", 0), 
                       stats["skipped"], stats["errors"], stats["inferred_workspaces"])
        else:
            logger.info("Ingestion complete: %d ingested, %d skipped, %d errors, %d workspaces inferred", 
                       stats["ingested"], stats["skipped"], stats["errors"], stats["inferred_workspaces"])
        
        return stats
    
    def _convert_claude_to_chat(self, conversation_data: Dict[str, Any]) -> Optional[Chat]:
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
        title = conversation_data.get("name") or conversation_data.get("summary") or "Untitled Chat"
        
        # Extract timestamps
        created_at = None
        if conversation_data.get("created_at"):
            try:
                # Parse ISO format timestamp
                created_at_str = conversation_data["created_at"]
                if created_at_str.endswith('Z'):
                    created_at_str = created_at_str[:-1] + '+00:00'
                created_at = datetime.fromisoformat(created_at_str)
            except (ValueError, TypeError) as e:
                logger.debug("Could not parse created_at: %s", e)
        
        last_updated_at = None
        if conversation_data.get("updated_at"):
            try:
                updated_at_str = conversation_data["updated_at"]
                if updated_at_str.endswith('Z'):
                    updated_at_str = updated_at_str[:-1] + '+00:00'
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
                    if created_at_str.endswith('Z'):
                        created_at_str = created_at_str[:-1] + '+00:00'
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
        
        # Extract model
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
            model=model,
        )
        
        return chat
    
    def _parse_claude_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
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
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str[:-1] + '+00:00'
            return datetime.fromisoformat(timestamp_str)
        except (ValueError, TypeError):
            return None
    
    def ingest_claude(self, progress_callback: Optional[callable] = None,
                      incremental: bool = False) -> Dict[str, int]:
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
        logger.info("Starting Claude.ai chat ingestion%s...", " (incremental)" if incremental else "")
        
        try:
            claude_reader = ClaudeReader()
        except ValueError as e:
            logger.error("Claude reader initialization failed: %s", e)
            logger.error("Please configure CLAUDE_ORG_ID and CLAUDE_SESSION_COOKIE")
            return {"ingested": 0, "skipped": 0, "errors": 1}
        
        stats = {"ingested": 0, "skipped": 0, "errors": 0}
        
        try:
            # Step 1: Get conversation list (1 API call)
            conversation_list = claude_reader.get_conversation_list()
            logger.info("Found %d Claude conversations", len(conversation_list))
            
            # Step 2: Filter if incremental
            conversations_to_fetch = []
            if incremental:
                for conv_meta in conversation_list:
                    conv_id = conv_meta.get("uuid")
                    if not conv_id:
                        continue
                    
                    api_updated_at = self._parse_claude_timestamp(conv_meta.get("updated_at"))
                    
                    # Check if we have this conversation and when it was last updated
                    db_chat = self.db.get_chat_by_composer_id(conv_id)
                    
                    if db_chat is None:
                        # New conversation
                        conversations_to_fetch.append(conv_meta)
                    elif api_updated_at and db_chat.get("last_updated_at"):
                        db_updated_at = datetime.fromisoformat(db_chat["last_updated_at"])
                        if api_updated_at > db_updated_at:
                            # Updated since we last stored it
                            conversations_to_fetch.append(conv_meta)
                        else:
                            stats["skipped"] += 1
                    else:
                        # Can't compare timestamps, fetch to be safe
                        conversations_to_fetch.append(conv_meta)
                
                logger.info("Incremental: %d new/updated, %d unchanged",
                           len(conversations_to_fetch), stats["skipped"])
            else:
                conversations_to_fetch = conversation_list
            
            total = len(conversations_to_fetch)
            logger.info("Processing %d conversations...", total)
            
            # Step 3: Fetch details only for filtered conversations
            for idx, conv_meta in enumerate(conversations_to_fetch, 1):
                conv_id = conv_meta.get("uuid", f"unknown-{idx}")
                
                if progress_callback and total:
                    progress_callback(conv_id, total, idx)
                
                try:
                    # Fetch full conversation details
                    full_conv = claude_reader._fetch_conversation_detail(conv_id)
                    if not full_conv:
                        stats["skipped"] += 1
                        continue
                    
                    # Merge metadata with full details
                    full_conv.update(conv_meta)
                    
                    # Convert to domain model
                    chat = self._convert_claude_to_chat(full_conv)
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
                        logger.info("Processed %d/%d Claude conversations...", idx, total)
                        
                except Exception as e:
                    logger.error("Error processing Claude conversation %s: %s", conv_id, e)
                    stats["errors"] += 1
            
            logger.info("Claude ingestion complete: %d ingested, %d skipped, %d errors",
                       stats["ingested"], stats["skipped"], stats["errors"])
            
        except Exception as e:
            logger.error("Error during Claude ingestion: %s", e)
            stats["errors"] += 1
        
        return stats

