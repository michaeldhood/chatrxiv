"""
Database layer for chat aggregation.

Provides SQLite database with FTS5 full-text search capabilities.
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.core.config import get_default_db_path
from src.core.models import Chat, Workspace

logger = logging.getLogger(__name__)


class ChatDatabase:
    """
    SQLite database for storing aggregated chat data.

    Provides methods for storing and querying chats, messages, and workspaces
    with full-text search capabilities via FTS5.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database connection.

        Parameters
        ----
        db_path : str, optional
            Path to database file. If None, uses default OS-specific location.
        """
        if db_path is None:
            db_path = str(get_default_db_path())

        self.db_path = db_path
        self.conn = None
        self._ensure_schema()

    def _ensure_schema(self):
        """Create database schema if it doesn't exist."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Enable WAL mode for concurrent read/write access
        # This allows the daemon (writer) and web server (reader) to access DB simultaneously
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.fetchone()  # Consume the result

        cursor = self.conn.cursor()

        # Projects table (for grouping workspaces)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Workspaces table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_hash TEXT UNIQUE NOT NULL,
                folder_uri TEXT,
                resolved_path TEXT,
                first_seen_at TEXT,
                last_seen_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                project_id INTEGER REFERENCES projects(id)
            )
        """)

        # Chats table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cursor_composer_id TEXT UNIQUE NOT NULL,
                workspace_id INTEGER,
                title TEXT,
                mode TEXT,
                created_at TEXT,
                last_updated_at TEXT,
                source TEXT DEFAULT 'cursor',
                messages_count INTEGER DEFAULT 0,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
            )
        """)

        # Migration: Add messages_count column if it doesn't exist
        cursor.execute("PRAGMA table_info(chats)")
        columns = [row[1] for row in cursor.fetchall()]
        if "messages_count" not in columns:
            cursor.execute(
                "ALTER TABLE chats ADD COLUMN messages_count INTEGER DEFAULT 0"
            )
            logger.info("Added messages_count column to chats table")

        # Migration: Add summary column if it doesn't exist
        if "summary" not in columns:
            cursor.execute("ALTER TABLE chats ADD COLUMN summary TEXT")
            logger.info("Added summary column to chats table")

        # Migration: Add project_id column to workspaces if it doesn't exist
        cursor.execute("PRAGMA table_info(workspaces)")
        workspace_columns = [row[1] for row in cursor.fetchall()]
        if "project_id" not in workspace_columns:
            cursor.execute(
                "ALTER TABLE workspaces ADD COLUMN project_id INTEGER REFERENCES projects(id)"
            )
            logger.info("Added project_id column to workspaces table")

        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                text TEXT,
                rich_text TEXT,
                created_at TEXT,
                cursor_bubble_id TEXT,
                raw_json TEXT,
                message_type TEXT DEFAULT 'response',
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)

        # Migration: Add message_type column if it doesn't exist
        cursor.execute("PRAGMA table_info(messages)")
        message_columns = [row[1] for row in cursor.fetchall()]
        if "message_type" not in message_columns:
            cursor.execute(
                "ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT 'response'"
            )
            logger.info("Added message_type column to messages table")

        # Chat files (relevant files per chat)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_files (
                chat_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                PRIMARY KEY (chat_id, path),
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)

        # Tags table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                chat_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (chat_id, tag),
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)

        # Plans table (metadata only)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                file_path TEXT,
                created_at TEXT,
                last_updated_at TEXT
            )
        """)

        # Junction table for chat-plan relationships
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_plans (
                chat_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL,
                relationship TEXT NOT NULL,
                PRIMARY KEY (chat_id, plan_id, relationship),
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
            )
        """)

        # FTS5 virtual table for full-text search on messages
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
                chat_id,
                text,
                rich_text,
                content='messages',
                content_rowid='id'
            )
        """)

        # NEW: Unified FTS5 table for Obsidian-like search across ALL content
        # Includes chat titles, message text, tags, and file paths
        # Uses prefix tokenizer for instant search-as-you-type
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS unified_fts USING fts5(
                chat_id UNINDEXED,
                content_type,
                title,
                message_text,
                tags,
                files,
                tokenize='porter unicode61'
            )
        """)

        # Triggers to keep FTS5 in sync
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO message_fts(chat_id, text, rich_text, rowid)
                VALUES (new.chat_id, new.text, new.rich_text, new.id);
            END
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO message_fts(message_fts, rowid, chat_id, text, rich_text)
                VALUES('delete', old.id, old.chat_id, old.text, old.rich_text);
            END
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                INSERT INTO message_fts(message_fts, rowid, chat_id, text, rich_text)
                VALUES('delete', old.id, old.chat_id, old.text, old.rich_text);
                INSERT INTO message_fts(chat_id, text, rich_text, rowid)
                VALUES (new.chat_id, new.text, new.rich_text, new.id);
            END
        """)

        # Ingestion state table for tracking incremental ingestion
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_state (
                source TEXT PRIMARY KEY,
                last_run_at TEXT,
                last_processed_timestamp TEXT,
                last_composer_id TEXT,
                stats_ingested INTEGER DEFAULT 0,
                stats_skipped INTEGER DEFAULT 0,
                stats_errors INTEGER DEFAULT 0
            )
        """)

        # Indexes for performance
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chats_composer_id ON chats(cursor_composer_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chats_workspace ON chats(workspace_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chats_created ON chats(created_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chats_updated ON chats(last_updated_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workspaces_hash ON workspaces(workspace_hash)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_workspaces_project ON workspaces(project_id)"
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_plans_plan_id ON plans(plan_id)")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_plans_chat ON chat_plans(chat_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_plans_plan ON chat_plans(plan_id)"
        )

        # Check if unified_fts needs to be rebuilt (migration for existing databases)
        cursor.execute("SELECT COUNT(*) FROM unified_fts")
        unified_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM chats")
        chat_count = cursor.fetchone()[0]
        if chat_count > 0 and unified_count == 0:
            logger.info("Rebuilding unified FTS index for %d chats...", chat_count)
            self._rebuild_unified_fts()

        self.conn.commit()
        logger.info("Database schema initialized at %s", self.db_path)

    def upsert_workspace(self, workspace: Workspace) -> int:
        """
        Insert or update a workspace.

        Parameters
        ----
        workspace : Workspace
            Workspace to upsert

        Returns
        ----
        int
            Workspace ID
        """
        cursor = self.conn.cursor()

        # Check if exists
        cursor.execute(
            "SELECT id FROM workspaces WHERE workspace_hash = ?",
            (workspace.workspace_hash,),
        )
        row = cursor.fetchone()

        if row:
            workspace_id = row[0]
            # Update
            cursor.execute(
                """
                UPDATE workspaces 
                SET folder_uri = ?, resolved_path = ?, last_seen_at = ?
                WHERE id = ?
            """,
                (
                    workspace.folder_uri,
                    workspace.resolved_path,
                    datetime.now().isoformat() if workspace.last_seen_at else None,
                    workspace_id,
                ),
            )
        else:
            # Insert
            cursor.execute(
                """
                INSERT INTO workspaces (workspace_hash, folder_uri, resolved_path, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    workspace.workspace_hash,
                    workspace.folder_uri,
                    workspace.resolved_path,
                    workspace.first_seen_at.isoformat()
                    if workspace.first_seen_at
                    else datetime.now().isoformat(),
                    workspace.last_seen_at.isoformat()
                    if workspace.last_seen_at
                    else datetime.now().isoformat(),
                ),
            )
            workspace_id = cursor.lastrowid

        self.conn.commit()
        return workspace_id

    def upsert_chat(self, chat: Chat) -> int:
        """
        Insert or update a chat and its messages.

        Parameters
        ----
        chat : Chat
            Chat to upsert

        Returns
        ----
        int
            Chat ID
        """
        cursor = self.conn.cursor()

        # Check if exists
        cursor.execute(
            "SELECT id FROM chats WHERE cursor_composer_id = ?",
            (chat.cursor_composer_id,),
        )
        row = cursor.fetchone()

        # Calculate message count
        messages_count = len(chat.messages)

        if row:
            chat_id = row[0]
            # Update chat metadata
            cursor.execute(
                """
                UPDATE chats 
                SET workspace_id = ?, title = ?, mode = ?, created_at = ?, last_updated_at = ?, source = ?, messages_count = ?
                WHERE id = ?
            """,
                (
                    chat.workspace_id,
                    chat.title or "",
                    chat.mode.value,
                    chat.created_at.isoformat() if chat.created_at else None,
                    chat.last_updated_at.isoformat() if chat.last_updated_at else None,
                    chat.source,
                    messages_count,
                    chat_id,
                ),
            )
            # Delete old messages
            cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            cursor.execute("DELETE FROM chat_files WHERE chat_id = ?", (chat_id,))
        else:
            # Insert
            cursor.execute(
                """
                INSERT INTO chats (cursor_composer_id, workspace_id, title, mode, created_at, last_updated_at, source, messages_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    chat.cursor_composer_id,
                    chat.workspace_id,
                    chat.title or "",
                    chat.mode.value,
                    chat.created_at.isoformat() if chat.created_at else None,
                    chat.last_updated_at.isoformat() if chat.last_updated_at else None,
                    chat.source,
                    messages_count,
                ),
            )
            chat_id = cursor.lastrowid

        # Insert messages
        for msg in chat.messages:
            cursor.execute(
                """
                INSERT INTO messages (chat_id, role, text, rich_text, created_at, cursor_bubble_id, raw_json, message_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    chat_id,
                    msg.role.value,
                    msg.text or "",
                    msg.rich_text or "",
                    msg.created_at.isoformat() if msg.created_at else None,
                    msg.cursor_bubble_id,
                    json.dumps(msg.raw_json) if msg.raw_json else None,
                    msg.message_type.value,
                ),
            )

        # Insert relevant files
        for file_path in chat.relevant_files:
            cursor.execute(
                """
                INSERT OR IGNORE INTO chat_files (chat_id, path)
                VALUES (?, ?)
            """,
                (chat_id, file_path),
            )

        self.conn.commit()

        # Update unified FTS index for instant search
        self._update_unified_fts(chat_id)

        return chat_id

    def search_chats(
        self, query: str, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Search chats using full-text search.

        Parameters
        ----
        query : str
            Search query
        limit : int
            Maximum number of results
        offset : int
            Offset for pagination

        Returns
        ----
        List[Dict[str, Any]]
            List of matching chats with metadata
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT c.id, c.cursor_composer_id, c.title, c.mode, c.created_at, c.source, c.messages_count,
                   w.workspace_hash, w.resolved_path
            FROM chats c
            LEFT JOIN workspaces w ON c.workspace_id = w.id
            INNER JOIN message_fts fts ON c.id = fts.chat_id
            WHERE message_fts MATCH ?
            ORDER BY c.created_at DESC
            LIMIT ? OFFSET ?
        """,
            (query, limit, offset),
        )

        results = []
        chat_ids = []
        for row in cursor.fetchall():
            chat_id = row[0]
            chat_ids.append(chat_id)
            results.append(
                {
                    "id": chat_id,
                    "composer_id": row[1],
                    "title": row[2],
                    "mode": row[3],
                    "created_at": row[4],
                    "source": row[5],
                    "messages_count": row[6] if len(row) > 6 else 0,
                    "workspace_hash": row[7] if len(row) > 7 else None,
                    "workspace_path": row[8] if len(row) > 8 else None,
                    "tags": [],  # Will be populated below
                }
            )

        # Load tags for all chats in batch
        if chat_ids:
            placeholders = ",".join(["?"] * len(chat_ids))
            cursor.execute(
                f"""
                SELECT chat_id, tag FROM tags 
                WHERE chat_id IN ({placeholders})
                ORDER BY chat_id, tag
            """,
                chat_ids,
            )

            # Group tags by chat_id
            tags_by_chat = {}
            for row in cursor.fetchall():
                chat_id, tag = row
                if chat_id not in tags_by_chat:
                    tags_by_chat[chat_id] = []
                tags_by_chat[chat_id].append(tag)

            # Assign tags to results
            for result in results:
                result["tags"] = tags_by_chat.get(result["id"], [])

        return results

    def get_chat(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a chat with all its messages.

        Parameters
        ----
        chat_id : int
            Chat ID

        Returns
        ----
        Dict[str, Any]
            Chat data with messages, or None if not found
        """
        cursor = self.conn.cursor()

        # Get chat - explicitly select columns to handle schema migration
        cursor.execute(
            """
            SELECT c.id, c.cursor_composer_id, c.workspace_id, c.title, c.mode, 
                   c.created_at, c.last_updated_at, c.source, c.messages_count,
                   c.summary, w.workspace_hash, w.resolved_path
            FROM chats c
            LEFT JOIN workspaces w ON c.workspace_id = w.id
            WHERE c.id = ?
        """,
            (chat_id,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        chat_data = {
            "id": row[0],
            "composer_id": row[1],
            "workspace_id": row[2],
            "title": row[3],
            "mode": row[4],
            "created_at": row[5],
            "last_updated_at": row[6],
            "source": row[7],
            "messages_count": row[8] if len(row) > 8 else 0,  # Handle migration case
            "summary": row[9] if len(row) > 9 else None,  # Handle migration case
            "workspace_hash": row[10] if len(row) > 10 else None,
            "workspace_path": row[11] if len(row) > 11 else None,
            "messages": [],
            "files": [],
        }

        # Get messages
        cursor.execute(
            """
            SELECT role, text, rich_text, created_at, cursor_bubble_id, message_type, raw_json
            FROM messages
            WHERE chat_id = ?
            ORDER BY created_at ASC
        """,
            (chat_id,),
        )

        for msg_row in cursor.fetchall():
            # Parse raw_json from JSON string back to dict
            raw_json_data = None
            if len(msg_row) > 6 and msg_row[6]:
                try:
                    raw_json_data = json.loads(msg_row[6])
                except (json.JSONDecodeError, TypeError):
                    raw_json_data = None

            chat_data["messages"].append(
                {
                    "role": msg_row[0],
                    "text": msg_row[1],
                    "rich_text": msg_row[2],
                    "created_at": msg_row[3],
                    "bubble_id": msg_row[4],
                    "message_type": msg_row[5]
                    if len(msg_row) > 5
                    else "response",  # Handle migration case
                    "raw_json": raw_json_data,
                }
            )

        # Get files
        cursor.execute("SELECT path FROM chat_files WHERE chat_id = ?", (chat_id,))
        chat_data["files"] = [row[0] for row in cursor.fetchall()]

        # Get tags
        cursor.execute(
            "SELECT tag FROM tags WHERE chat_id = ? ORDER BY tag", (chat_id,)
        )
        chat_data["tags"] = [row[0] for row in cursor.fetchall()]

        return chat_data

    def update_chat_summary(self, chat_id: int, summary: str) -> None:
        """
        Update the summary for a chat.

        Parameters
        ----
        chat_id : int
            Chat ID
        summary : str
            Summary text to store
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE chats SET summary = ? WHERE id = ?",
            (summary, chat_id),
        )
        self.conn.commit()

    def count_chats(
        self,
        workspace_id: Optional[int] = None,
        empty_filter: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> int:
        """
        Count total chats, optionally filtered by workspace, project, and empty status.

        Parameters
        ----
        workspace_id : int, optional
            Filter by workspace
        empty_filter : str, optional
            Filter by empty status: 'empty' (messages_count = 0), 'non_empty' (messages_count > 0), or None (all)
        project_id : int, optional
            Filter by project (matches chats in any workspace belonging to this project)

        Returns
        ----
        int
            Total count of chats
        """
        cursor = self.conn.cursor()

        conditions = []
        params = []
        joins = ""

        if workspace_id:
            conditions.append("c.workspace_id = ?")
            params.append(workspace_id)

        if project_id:
            joins = "INNER JOIN workspaces w ON c.workspace_id = w.id"
            conditions.append("w.project_id = ?")
            params.append(project_id)

        if empty_filter == "empty":
            conditions.append("c.messages_count = 0")
        elif empty_filter == "non_empty":
            conditions.append("c.messages_count > 0")

        query = f"SELECT COUNT(*) FROM chats c {joins}"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor.execute(query, params)
        return cursor.fetchone()[0]

    def count_search(self, query: str) -> int:
        """
        Count search results for a query.

        Parameters
        ----
        query : str
            Search query (FTS5 syntax)

        Returns
        ----
        int
            Total count of matching chats
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(DISTINCT c.id)
            FROM chats c
            INNER JOIN message_fts fts ON c.id = fts.chat_id
            WHERE message_fts MATCH ?
        """,
            (query,),
        )

        return cursor.fetchone()[0]

    def list_chats(
        self,
        workspace_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
        empty_filter: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        List chats with optional filtering.

        Parameters
        ----
        workspace_id : int, optional
            Filter by workspace
        limit : int
            Maximum number of results
        offset : int
            Offset for pagination
        empty_filter : str, optional
            Filter by empty status: 'empty' (messages_count = 0), 'non_empty' (messages_count > 0), or None (all)
        project_id : int, optional
            Filter by project (matches chats in any workspace belonging to this project)

        Returns
        ----
        List[Dict[str, Any]]
            List of chats
        """
        cursor = self.conn.cursor()

        conditions = []
        params = []

        if workspace_id:
            conditions.append("c.workspace_id = ?")
            params.append(workspace_id)

        if project_id:
            conditions.append("w.project_id = ?")
            params.append(project_id)

        if empty_filter == "empty":
            conditions.append("c.messages_count = 0")
        elif empty_filter == "non_empty":
            conditions.append("c.messages_count > 0")

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Use INNER JOIN when filtering by project to exclude unassigned workspaces
        join_type = "INNER JOIN" if project_id else "LEFT JOIN"

        query = f"""
            SELECT c.id, c.cursor_composer_id, c.title, c.mode, c.created_at, c.source, c.messages_count,
                   w.workspace_hash, w.resolved_path
            FROM chats c
            {join_type} workspaces w ON c.workspace_id = w.id
            {where_clause}
            ORDER BY c.created_at DESC
            LIMIT ? OFFSET ?
        """

        params.extend([limit, offset])
        cursor.execute(query, params)

        results = []
        chat_ids = []
        for row in cursor.fetchall():
            chat_id = row[0]
            chat_ids.append(chat_id)
            results.append(
                {
                    "id": chat_id,
                    "composer_id": row[1],
                    "title": row[2],
                    "mode": row[3],
                    "created_at": row[4],
                    "source": row[5],
                    "messages_count": row[6],
                    "workspace_hash": row[7],
                    "workspace_path": row[8],
                    "tags": [],  # Will be populated below
                }
            )

        # Load tags for all chats in batch
        if chat_ids:
            placeholders = ",".join(["?"] * len(chat_ids))
            cursor.execute(
                f"""
                SELECT chat_id, tag FROM tags 
                WHERE chat_id IN ({placeholders})
                ORDER BY chat_id, tag
            """,
                chat_ids,
            )

            # Group tags by chat_id
            tags_by_chat = {}
            for row in cursor.fetchall():
                chat_id, tag = row
                if chat_id not in tags_by_chat:
                    tags_by_chat[chat_id] = []
                tags_by_chat[chat_id].append(tag)

            # Assign tags to results
            for result in results:
                result["tags"] = tags_by_chat.get(result["id"], [])

        return results

    def get_filter_options(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all available filter options for the UI.

        Returns distinct values for sources and modes with their counts.
        Used to populate filter dropdowns regardless of current pagination.

        Returns
        ----
        Dict[str, List[Dict[str, Any]]]
            Dictionary with 'sources' and 'modes' keys, each containing
            a list of {value, count} objects sorted by count descending.
        """
        cursor = self.conn.cursor()

        # Get distinct sources with counts
        cursor.execute("""
            SELECT source, COUNT(*) as count
            FROM chats
            WHERE source IS NOT NULL AND source != ''
            GROUP BY source
            ORDER BY count DESC
        """)
        sources = [{"value": row[0], "count": row[1]} for row in cursor.fetchall()]

        # Get distinct modes with counts
        cursor.execute("""
            SELECT mode, COUNT(*) as count
            FROM chats
            WHERE mode IS NOT NULL AND mode != ''
            GROUP BY mode
            ORDER BY count DESC
        """)
        modes = [{"value": row[0], "count": row[1]} for row in cursor.fetchall()]

        return {"sources": sources, "modes": modes}

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # ========================================================================
    # Project Management Methods
    # ========================================================================

    def create_project(self, name: str, description: Optional[str] = None) -> int:
        """
        Create a new project.

        Parameters
        ----
        name : str
            Unique project name
        description : str, optional
            Project description

        Returns
        ----
        int
            The new project's ID

        Raises
        ----
        sqlite3.IntegrityError
            If project name already exists
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO projects (name, description)
            VALUES (?, ?)
        """,
            (name, description),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a project by ID.

        Parameters
        ----
        project_id : int
            Project ID

        Returns
        ----
        Dict[str, Any], optional
            Project data or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, name, description, created_at
            FROM projects
            WHERE id = ?
        """,
            (project_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "created_at": row[3],
        }

    def get_project_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a project by name.

        Parameters
        ----
        name : str
            Project name

        Returns
        ----
        Dict[str, Any], optional
            Project data or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, name, description, created_at
            FROM projects
            WHERE name = ?
        """,
            (name,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "created_at": row[3],
        }

    def list_projects(self) -> List[Dict[str, Any]]:
        """
        List all projects with workspace counts.

        Returns
        ----
        List[Dict[str, Any]]
            List of projects with workspace counts
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT p.id, p.name, p.description, p.created_at,
                   COUNT(w.id) as workspace_count
            FROM projects p
            LEFT JOIN workspaces w ON w.project_id = p.id
            GROUP BY p.id
            ORDER BY p.name
        """)
        return [
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "created_at": row[3],
                "workspace_count": row[4],
            }
            for row in cursor.fetchall()
        ]

    def delete_project(self, project_id: int) -> bool:
        """
        Delete a project. Workspaces are unlinked but not deleted.

        Parameters
        ----
        project_id : int
            Project ID to delete

        Returns
        ----
        bool
            True if project was deleted, False if not found
        """
        cursor = self.conn.cursor()
        # Unlink workspaces first
        cursor.execute(
            """
            UPDATE workspaces SET project_id = NULL WHERE project_id = ?
        """,
            (project_id,),
        )
        # Delete project
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def assign_workspace_to_project(self, workspace_id: int, project_id: int) -> None:
        """
        Assign a workspace to a project.

        Parameters
        ----
        workspace_id : int
            Workspace ID
        project_id : int
            Project ID to assign to
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE workspaces SET project_id = ? WHERE id = ?
        """,
            (project_id, workspace_id),
        )
        self.conn.commit()

    def assign_workspace_to_project_by_hash(
        self, workspace_hash: str, project_id: int
    ) -> bool:
        """
        Assign a workspace to a project by workspace hash.

        Parameters
        ----
        workspace_hash : str
            Workspace hash
        project_id : int
            Project ID to assign to

        Returns
        ----
        bool
            True if workspace was found and updated
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            UPDATE workspaces SET project_id = ? WHERE workspace_hash = ?
        """,
            (project_id, workspace_hash),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_workspaces_by_project(self, project_id: int) -> List[Dict[str, Any]]:
        """
        Get all workspaces in a project.

        Parameters
        ----
        project_id : int
            Project ID

        Returns
        ----
        List[Dict[str, Any]]
            List of workspace records
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, workspace_hash, folder_uri, resolved_path, 
                   first_seen_at, last_seen_at, project_id
            FROM workspaces
            WHERE project_id = ?
            ORDER BY resolved_path
        """,
            (project_id,),
        )
        return [
            {
                "id": row[0],
                "workspace_hash": row[1],
                "folder_uri": row[2],
                "resolved_path": row[3],
                "first_seen_at": row[4],
                "last_seen_at": row[5],
                "project_id": row[6],
            }
            for row in cursor.fetchall()
        ]

    def get_workspace_by_hash(self, workspace_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get a workspace by its hash.

        Parameters
        ----
        workspace_hash : str
            Workspace hash

        Returns
        ----
        Dict[str, Any], optional
            Workspace data or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, workspace_hash, folder_uri, resolved_path, 
                   first_seen_at, last_seen_at, project_id
            FROM workspaces
            WHERE workspace_hash = ?
        """,
            (workspace_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "workspace_hash": row[1],
            "folder_uri": row[2],
            "resolved_path": row[3],
            "first_seen_at": row[4],
            "last_seen_at": row[5],
            "project_id": row[6],
        }

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """
        List all workspaces with their project associations.

        Returns
        ----
        List[Dict[str, Any]]
            List of workspace records with project info
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT w.id, w.workspace_hash, w.folder_uri, w.resolved_path, 
                   w.first_seen_at, w.last_seen_at, w.project_id,
                   p.name as project_name
            FROM workspaces w
            LEFT JOIN projects p ON w.project_id = p.id
            ORDER BY w.resolved_path
        """)
        return [
            {
                "id": row[0],
                "workspace_hash": row[1],
                "folder_uri": row[2],
                "resolved_path": row[3],
                "first_seen_at": row[4],
                "last_seen_at": row[5],
                "project_id": row[6],
                "project_name": row[7],
            }
            for row in cursor.fetchall()
        ]

    def get_ingestion_state(self, source: str = "cursor") -> Optional[Dict[str, Any]]:
        """
        Get ingestion state for a source.

        Parameters
        ----
        source : str
            Source name (e.g., "cursor", "claude")

        Returns
        ----
        Dict[str, Any], optional
            Ingestion state or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT last_run_at, last_processed_timestamp, last_composer_id,
                   stats_ingested, stats_skipped, stats_errors
            FROM ingestion_state
            WHERE source = ?
        """,
            (source,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return {
            "last_run_at": row[0],
            "last_processed_timestamp": row[1],
            "last_composer_id": row[2],
            "stats_ingested": row[3] or 0,
            "stats_skipped": row[4] or 0,
            "stats_errors": row[5] or 0,
        }

    def update_ingestion_state(
        self,
        source: str,
        last_run_at: Optional[datetime] = None,
        last_processed_timestamp: Optional[str] = None,
        last_composer_id: Optional[str] = None,
        stats: Optional[Dict[str, int]] = None,
    ):
        """
        Update ingestion state for a source.

        Parameters
        ----
        source : str
            Source name
        last_run_at : datetime, optional
            When ingestion last ran
        last_processed_timestamp : str, optional
            Last processed timestamp (ISO format)
        last_composer_id : str, optional
            Last processed composer ID
        stats : Dict[str, int], optional
            Statistics from last run
        """
        cursor = self.conn.cursor()

        # Check if exists
        cursor.execute("SELECT source FROM ingestion_state WHERE source = ?", (source,))
        exists = cursor.fetchone() is not None

        if exists:
            # Update
            updates = []
            params = []

            if last_run_at is not None:
                updates.append("last_run_at = ?")
                params.append(last_run_at.isoformat())

            if last_processed_timestamp is not None:
                updates.append("last_processed_timestamp = ?")
                params.append(last_processed_timestamp)

            if last_composer_id is not None:
                updates.append("last_composer_id = ?")
                params.append(last_composer_id)

            if stats:
                if "ingested" in stats:
                    updates.append("stats_ingested = ?")
                    params.append(stats["ingested"])
                if "skipped" in stats:
                    updates.append("stats_skipped = ?")
                    params.append(stats["skipped"])
                if "errors" in stats:
                    updates.append("stats_errors = ?")
                    params.append(stats["errors"])

            if updates:
                params.append(source)
                cursor.execute(
                    f"UPDATE ingestion_state SET {', '.join(updates)} WHERE source = ?",
                    params,
                )
        else:
            # Insert
            cursor.execute(
                """
                INSERT INTO ingestion_state 
                (source, last_run_at, last_processed_timestamp, last_composer_id, 
                 stats_ingested, stats_skipped, stats_errors)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    source,
                    last_run_at.isoformat() if last_run_at else None,
                    last_processed_timestamp,
                    last_composer_id,
                    stats.get("ingested", 0) if stats else 0,
                    stats.get("skipped", 0) if stats else 0,
                    stats.get("errors", 0) if stats else 0,
                ),
            )

        self.conn.commit()

    def get_chats_updated_since(
        self, timestamp: datetime, source: str = "cursor"
    ) -> List[str]:
        """
        Get composer IDs of chats updated since a timestamp.

        Useful for incremental ingestion - only process chats that have been updated.

        Parameters
        ----
        timestamp : datetime
            Timestamp to compare against
        source : str
            Source filter (e.g., "cursor")

        Returns
        ----
        List[str]
            List of composer IDs
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT cursor_composer_id
            FROM chats
            WHERE source = ? AND last_updated_at > ?
            ORDER BY last_updated_at ASC
        """,
            (source, timestamp.isoformat()),
        )

        return [row[0] for row in cursor.fetchall()]

    def get_chat_by_composer_id(self, composer_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a chat by its cursor_composer_id.

        Parameters
        ----
        composer_id : str
            Composer/conversation ID to look up

        Returns
        ----
        Dict[str, Any], optional
            Chat record with id, cursor_composer_id, last_updated_at, and source,
            or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, cursor_composer_id, last_updated_at, source
            FROM chats WHERE cursor_composer_id = ?
        """,
            (composer_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "cursor_composer_id": row[1],
            "last_updated_at": row[2],
            "source": row[3],
        }

    def get_last_updated_at(self) -> Optional[str]:
        """
        Get the most recent last_updated_at timestamp across all chats.

        Useful for detecting when new chats have been ingested.

        Returns
        ----
        str, optional
            ISO format timestamp of most recent update, or None if no chats exist
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT MAX(last_updated_at) FROM chats")
        result = cursor.fetchone()
        return result[0] if result and result[0] else None

    def add_tags(self, chat_id: int, tags: List[str]) -> None:
        """
        Add tags to a chat.

        Parameters
        ----
        chat_id : int
            Chat ID
        tags : List[str]
            List of tags to add
        """
        cursor = self.conn.cursor()
        for tag in tags:
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO tags (chat_id, tag) VALUES (?, ?)",
                    (chat_id, tag),
                )
            except sqlite3.IntegrityError:
                # Tag already exists, ignore
                pass
        self.conn.commit()

    def remove_tags(self, chat_id: int, tags: List[str]) -> None:
        """
        Remove tags from a chat.

        Parameters
        ----
        chat_id : int
            Chat ID
        tags : List[str]
            List of tags to remove
        """
        cursor = self.conn.cursor()
        cursor.executemany(
            "DELETE FROM tags WHERE chat_id = ? AND tag = ?",
            [(chat_id, tag) for tag in tags],
        )
        self.conn.commit()

    def get_chat_tags(self, chat_id: int) -> List[str]:
        """
        Get all tags for a chat.

        Parameters
        ----
        chat_id : int
            Chat ID

        Returns
        ----
        List[str]
            List of tags
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT tag FROM tags WHERE chat_id = ? ORDER BY tag", (chat_id,)
        )
        return [row[0] for row in cursor.fetchall()]

    def get_all_tags(self) -> Dict[str, int]:
        """
        Get all unique tags with their frequency.

        Returns
        ----
        Dict[str, int]
            Dictionary mapping tags to their occurrence count
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT tag, COUNT(*) as count FROM tags GROUP BY tag ORDER BY count DESC"
        )
        return {row[0]: row[1] for row in cursor.fetchall()}

    def find_chats_by_tag(self, tag: str) -> List[int]:
        """
        Find all chat IDs with a specific tag.

        Parameters
        ----
        tag : str
            Tag to search for (supports SQL LIKE wildcards: %)

        Returns
        ----
        List[int]
            List of chat IDs
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT chat_id FROM tags WHERE tag LIKE ?", (tag,))
        return [row[0] for row in cursor.fetchall()]

    def get_chat_files(self, chat_id: int) -> List[str]:
        """
        Get all file paths associated with a chat.

        Parameters
        ----
        chat_id : int
            Chat ID

        Returns
        ----
        List[str]
            List of file paths
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT path FROM chat_files WHERE chat_id = ?", (chat_id,))
        return [row[0] for row in cursor.fetchall()]

    def upsert_plan(
        self,
        plan_id: str,
        name: str,
        file_path: Optional[str] = None,
        created_at: Optional[str] = None,
        last_updated_at: Optional[str] = None,
    ) -> int:
        """
        Insert or update a plan.

        Parameters
        ----
        plan_id : str
            Unique plan identifier (e.g., "complete_chatrxiv_migration_f77a44d3")
        name : str
            Plan name
        file_path : str, optional
            Path to the .plan.md file
        created_at : str, optional
            ISO timestamp when plan was created
        last_updated_at : str, optional
            ISO timestamp when plan was last updated

        Returns
        ----
        int
            Plan database ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO plans (plan_id, name, file_path, created_at, last_updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(plan_id) DO UPDATE SET
                name = excluded.name,
                file_path = excluded.file_path,
                last_updated_at = excluded.last_updated_at
            """,
            (plan_id, name, file_path, created_at, last_updated_at),
        )
        self.conn.commit()
        cursor.execute("SELECT id FROM plans WHERE plan_id = ?", (plan_id,))
        return cursor.fetchone()[0]

    def link_chat_to_plan(self, chat_id: int, plan_id: int, relationship: str) -> None:
        """
        Link a chat to a plan with a specific relationship.

        Parameters
        ----
        chat_id : int
            Chat database ID
        plan_id : int
            Plan database ID
        relationship : str
            Relationship type: 'created', 'edited', or 'referenced'
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO chat_plans (chat_id, plan_id, relationship)
            VALUES (?, ?, ?)
            """,
            (chat_id, plan_id, relationship),
        )
        self.conn.commit()

    def get_plans_for_chat(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        Get all plans linked to a chat.

        Parameters
        ----
        chat_id : int
            Chat database ID

        Returns
        ----
        List[Dict[str, Any]]
            List of plan dictionaries with relationship info
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT p.id, p.plan_id, p.name, p.file_path, p.created_at, p.last_updated_at,
                   cp.relationship
            FROM plans p
            JOIN chat_plans cp ON p.id = cp.plan_id
            WHERE cp.chat_id = ?
            ORDER BY p.created_at DESC
            """,
            (chat_id,),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "plan_id": row[1],
                "name": row[2],
                "file_path": row[3],
                "created_at": row[4],
                "last_updated_at": row[5],
                "relationship": row[6],
            }
            for row in rows
        ]

    def get_chats_for_plan(self, plan_id: int) -> List[Dict[str, Any]]:
        """
        Get all chats linked to a plan.

        Parameters
        ----
        plan_id : int
            Plan database ID

        Returns
        ----
        List[Dict[str, Any]]
            List of chat dictionaries with relationship info
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT c.id, c.cursor_composer_id, c.title, c.mode, c.created_at,
                   c.last_updated_at, cp.relationship
            FROM chats c
            JOIN chat_plans cp ON c.id = cp.chat_id
            WHERE cp.plan_id = ?
            ORDER BY c.created_at DESC
            """,
            (plan_id,),
        )
        rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "cursor_composer_id": row[1],
                "title": row[2],
                "mode": row[3],
                "created_at": row[4],
                "last_updated_at": row[5],
                "relationship": row[6],
            }
            for row in rows
        ]

    def _rebuild_unified_fts(self):
        """Rebuild the unified FTS index from all existing data."""
        cursor = self.conn.cursor()

        # Clear existing unified FTS data
        cursor.execute("DELETE FROM unified_fts")

        # Get all chats with their messages, tags, and files
        cursor.execute("""
            SELECT c.id, c.title
            FROM chats c
        """)
        chats = cursor.fetchall()

        for chat_id, title in chats:
            # Get all message text for this chat
            cursor.execute(
                """
                SELECT GROUP_CONCAT(text, ' ') 
                FROM messages 
                WHERE chat_id = ?
            """,
                (chat_id,),
            )
            message_text = cursor.fetchone()[0] or ""

            # Get tags
            cursor.execute(
                """
                SELECT GROUP_CONCAT(tag, ' ')
                FROM tags
                WHERE chat_id = ?
            """,
                (chat_id,),
            )
            tags = cursor.fetchone()[0] or ""

            # Get files
            cursor.execute(
                """
                SELECT GROUP_CONCAT(path, ' ')
                FROM chat_files
                WHERE chat_id = ?
            """,
                (chat_id,),
            )
            files = cursor.fetchone()[0] or ""

            # Insert into unified FTS
            cursor.execute(
                """
                INSERT INTO unified_fts (chat_id, content_type, title, message_text, tags, files)
                VALUES (?, 'chat', ?, ?, ?, ?)
            """,
                (chat_id, title or "", message_text, tags, files),
            )

        self.conn.commit()
        logger.info("Rebuilt unified FTS index with %d chats", len(chats))

    def _update_unified_fts(self, chat_id: int):
        """Update unified FTS entry for a specific chat."""
        cursor = self.conn.cursor()

        # Delete existing entry
        cursor.execute("DELETE FROM unified_fts WHERE chat_id = ?", (chat_id,))

        # Get chat title
        cursor.execute("SELECT title FROM chats WHERE id = ?", (chat_id,))
        row = cursor.fetchone()
        if not row:
            return
        title = row[0] or ""

        # Get all message text
        cursor.execute(
            """
            SELECT GROUP_CONCAT(text, ' ')
            FROM messages
            WHERE chat_id = ?
        """,
            (chat_id,),
        )
        message_text = cursor.fetchone()[0] or ""

        # Get tags
        cursor.execute(
            """
            SELECT GROUP_CONCAT(tag, ' ')
            FROM tags
            WHERE chat_id = ?
        """,
            (chat_id,),
        )
        tags = cursor.fetchone()[0] or ""

        # Get files
        cursor.execute(
            """
            SELECT GROUP_CONCAT(path, ' ')
            FROM chat_files
            WHERE chat_id = ?
        """,
            (chat_id,),
        )
        files = cursor.fetchone()[0] or ""

        # Insert updated entry
        cursor.execute(
            """
            INSERT INTO unified_fts (chat_id, content_type, title, message_text, tags, files)
            VALUES (?, 'chat', ?, ?, ?, ?)
        """,
            (chat_id, title, message_text, tags, files),
        )

        self.conn.commit()

    # BM25 column weights for unified_fts
    # Columns (indexed only): content_type, title, message_text, tags, files
    # We heavily weight title matches to ensure exact title matches rank at the top
    BM25_WEIGHTS = (
        0.5,   # content_type - low (always "chat", doesn't differentiate)
        10.0,  # title - HIGH (key for matching chat by name)
        1.0,   # message_text - baseline
        3.0,   # tags - moderately boosted (semantic markers)
        1.0,   # files - baseline
    )

    def instant_search(
        self, query: str, limit: int = 20, sort_by: str = "relevance"
    ) -> List[Dict[str, Any]]:
        """
        Fast instant search for typeahead/live search.

        Searches across chat titles, messages, tags, and files.
        Returns results with highlighted snippets.

        Parameters
        ----
        query : str
            Search query (automatically handles prefix matching)
        limit : int
            Maximum results to return
        sort_by : str
            Sort order: 'relevance' (BM25) or 'date' (newest first)

        Returns
        ----
        List[Dict[str, Any]]
            Search results with snippets and highlights
        """
        cursor = self.conn.cursor()

        # Clean the query and add prefix matching for each term
        # This enables search-as-you-type behavior
        terms = query.strip().split()
        if not terms:
            return []

        # Build FTS5 query with prefix matching on last term
        # e.g., "hello wor" -> 'hello wor*'
        fts_query = " ".join(terms[:-1] + [terms[-1] + "*"]) if terms else ""

        # Clean query for title matching (used for boosting exact matches)
        clean_query = query.strip().lower()

        # Determine sort order
        # For relevance sorting, we use a compound ORDER BY:
        # 1. Exact title match (highest priority)
        # 2. Title starts with query
        # 3. Title contains query
        # 4. BM25 weighted score
        if sort_by == "date":
            order_clause = "ORDER BY c.created_at DESC"
        else:
            # title_boost: 0 = exact match, 1 = starts with, 2 = contains, 3 = no title match
            order_clause = "ORDER BY title_boost, rank"

        # Build BM25 function call with column weights
        bm25_call = f"bm25(unified_fts, {', '.join(str(w) for w in self.BM25_WEIGHTS)})"

        try:
            # Search with snippet generation
            # snippet() function: table, column_idx, start_mark, end_mark, ellipsis, max_tokens
            cursor.execute(
                f"""
                SELECT 
                    fts.chat_id,
                    c.cursor_composer_id,
                    c.title,
                    c.mode,
                    c.created_at,
                    c.source,
                    c.messages_count,
                    w.workspace_hash,
                    w.resolved_path,
                    snippet(unified_fts, 3, '<mark>', '</mark>', '...', 32) as snippet,
                    {bm25_call} as rank,
                    CASE
                        WHEN LOWER(c.title) = ? THEN 0
                        WHEN LOWER(c.title) LIKE ? || '%' THEN 1
                        WHEN LOWER(c.title) LIKE '%' || ? || '%' THEN 2
                        ELSE 3
                    END as title_boost
                FROM unified_fts fts
                INNER JOIN chats c ON fts.chat_id = c.id
                LEFT JOIN workspaces w ON c.workspace_id = w.id
                WHERE unified_fts MATCH ?
                {order_clause}
                LIMIT ?
            """,
                (clean_query, clean_query, clean_query, fts_query, limit),
            )

            results = []
            chat_ids = []
            for row in cursor.fetchall():
                chat_id = row[0]
                chat_ids.append(chat_id)
                results.append(
                    {
                        "id": chat_id,
                        "composer_id": row[1],
                        "title": row[2] or "Untitled Chat",
                        "mode": row[3],
                        "created_at": row[4],
                        "source": row[5],
                        "messages_count": row[6] or 0,
                        "workspace_hash": row[7],
                        "workspace_path": row[8],
                        "snippet": row[9],  # Highlighted snippet
                        "rank": row[10],
                        "tags": [],
                    }
                )

            # Batch load tags
            if chat_ids:
                placeholders = ",".join(["?"] * len(chat_ids))
                cursor.execute(
                    f"""
                    SELECT chat_id, tag FROM tags 
                    WHERE chat_id IN ({placeholders})
                    ORDER BY chat_id, tag
                """,
                    chat_ids,
                )

                tags_by_chat = {}
                for row in cursor.fetchall():
                    chat_id, tag = row
                    if chat_id not in tags_by_chat:
                        tags_by_chat[chat_id] = []
                    tags_by_chat[chat_id].append(tag)

                for result in results:
                    result["tags"] = tags_by_chat.get(result["id"], [])

            return results

        except sqlite3.OperationalError as e:
            # Handle malformed FTS queries gracefully
            logger.debug("FTS query error for '%s': %s", query, e)
            return []

    def search_with_snippets(
        self, query: str, limit: int = 50, offset: int = 0, sort_by: str = "relevance"
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Full search with snippets, pagination, and total count.

        Parameters
        ----
        query : str
            Search query
        limit : int
            Maximum results per page
        offset : int
            Pagination offset
        sort_by : str
            Sort order: 'relevance' (BM25) or 'date' (newest first)

        Returns
        ----
        Tuple[List[Dict], int]
            (results with snippets, total count)
        """
        cursor = self.conn.cursor()

        terms = query.strip().split()
        if not terms:
            return [], 0

        # Add prefix matching to last term
        fts_query = " ".join(terms[:-1] + [terms[-1] + "*"]) if terms else ""

        # Clean query for title matching (used for boosting exact matches)
        clean_query = query.strip().lower()

        # Determine sort order
        # For relevance sorting, we use a compound ORDER BY:
        # 1. Exact title match (highest priority)
        # 2. Title starts with query
        # 3. Title contains query
        # 4. BM25 weighted score
        if sort_by == "date":
            order_clause = "ORDER BY c.created_at DESC"
        else:
            order_clause = "ORDER BY title_boost, rank"

        # Build BM25 function call with column weights
        bm25_call = f"bm25(unified_fts, {', '.join(str(w) for w in self.BM25_WEIGHTS)})"

        try:
            # Get total count first
            cursor.execute(
                """
                SELECT COUNT(DISTINCT chat_id)
                FROM unified_fts
                WHERE unified_fts MATCH ?
            """,
                (fts_query,),
            )
            total = cursor.fetchone()[0]

            # Get results with snippets
            cursor.execute(
                f"""
                SELECT 
                    fts.chat_id,
                    c.cursor_composer_id,
                    c.title,
                    c.mode,
                    c.created_at,
                    c.source,
                    c.messages_count,
                    w.workspace_hash,
                    w.resolved_path,
                    snippet(unified_fts, 3, '<mark>', '</mark>', '...', 64) as snippet,
                    {bm25_call} as rank,
                    CASE
                        WHEN LOWER(c.title) = ? THEN 0
                        WHEN LOWER(c.title) LIKE ? || '%' THEN 1
                        WHEN LOWER(c.title) LIKE '%' || ? || '%' THEN 2
                        ELSE 3
                    END as title_boost
                FROM unified_fts fts
                INNER JOIN chats c ON fts.chat_id = c.id
                LEFT JOIN workspaces w ON c.workspace_id = w.id
                WHERE unified_fts MATCH ?
                {order_clause}
                LIMIT ? OFFSET ?
            """,
                (clean_query, clean_query, clean_query, fts_query, limit, offset),
            )

            results = []
            chat_ids = []
            for row in cursor.fetchall():
                chat_id = row[0]
                chat_ids.append(chat_id)
                results.append(
                    {
                        "id": chat_id,
                        "composer_id": row[1],
                        "title": row[2] or "Untitled Chat",
                        "mode": row[3],
                        "created_at": row[4],
                        "source": row[5],
                        "messages_count": row[6] or 0,
                        "workspace_hash": row[7],
                        "workspace_path": row[8],
                        "snippet": row[9],
                        "rank": row[10],
                        "tags": [],
                    }
                )

            # Batch load tags
            if chat_ids:
                placeholders = ",".join(["?"] * len(chat_ids))
                cursor.execute(
                    f"""
                    SELECT chat_id, tag FROM tags 
                    WHERE chat_id IN ({placeholders})
                    ORDER BY chat_id, tag
                """,
                    chat_ids,
                )

                tags_by_chat = {}
                for row in cursor.fetchall():
                    chat_id, tag = row
                    if chat_id not in tags_by_chat:
                        tags_by_chat[chat_id] = []
                    tags_by_chat[chat_id].append(tag)

                for result in results:
                    result["tags"] = tags_by_chat.get(result["id"], [])

            return results, total

        except sqlite3.OperationalError as e:
            logger.debug("FTS query error for '%s': %s", query, e)
            return [], 0

    def get_search_tag_facets(
        self,
        query: str,
        tag_filters: Optional[List[str]] = None,
        workspace_filters: Optional[List[int]] = None,
    ) -> Dict[str, int]:
        """
        Get tag facet counts for search results.

        Returns counts of all tags across ALL matching chats (not just current page),
        useful for building filter UI sidebars.

        Parameters
        ----
        query : str
            Search query
        tag_filters : List[str], optional
            If provided, only count tags for chats that have ALL these tags
        workspace_filters : List[int], optional
            If provided, only count tags for chats in these workspaces

        Returns
        ----
        Dict[str, int]
            Mapping of tag -> count of chats with that tag
        """
        cursor = self.conn.cursor()

        terms = query.strip().split()
        if not terms:
            return {}

        # Add prefix matching to last term
        fts_query = " ".join(terms[:-1] + [terms[-1] + "*"]) if terms else ""

        try:
            # Build conditions for matching chat IDs
            conditions = ["unified_fts MATCH ?"]
            params = [fts_query]

            if tag_filters:
                # Get chat IDs matching both FTS query AND all tag filters
                placeholders = ",".join(["?"] * len(tag_filters))
                tag_subquery = f"""
                    SELECT chat_id 
                    FROM tags 
                    WHERE tag IN ({placeholders})
                    GROUP BY chat_id
                    HAVING COUNT(DISTINCT tag) = ?
                """
                conditions.append(f"fts.chat_id IN ({tag_subquery})")
                params.extend(tag_filters)
                params.append(len(tag_filters))

            if workspace_filters:
                workspace_placeholders = ",".join(["?"] * len(workspace_filters))
                conditions.append(f"c.workspace_id IN ({workspace_placeholders})")
                params.extend(workspace_filters)

            where_clause = " AND ".join(conditions)

            if tag_filters or workspace_filters:
                cursor.execute(
                    f"""
                    SELECT DISTINCT fts.chat_id
                    FROM unified_fts fts
                    INNER JOIN chats c ON fts.chat_id = c.id
                    WHERE {where_clause}
                """,
                    params,
                )
            else:
                cursor.execute(
                    """
                    SELECT DISTINCT chat_id
                    FROM unified_fts
                    WHERE unified_fts MATCH ?
                """,
                    (fts_query,),
                )

            matching_chat_ids = [row[0] for row in cursor.fetchall()]

            if not matching_chat_ids:
                return {}

            # Get tag counts for matching chats
            placeholders = ",".join(["?"] * len(matching_chat_ids))
            cursor.execute(
                f"""
                SELECT tag, COUNT(*) as cnt
                FROM tags
                WHERE chat_id IN ({placeholders})
                GROUP BY tag
                ORDER BY cnt DESC, tag ASC
            """,
                matching_chat_ids,
            )

            return {row[0]: row[1] for row in cursor.fetchall()}

        except sqlite3.OperationalError as e:
            logger.debug("FTS facet query error for '%s': %s", query, e)
            return {}

    def get_search_workspace_facets(
        self,
        query: str,
        tag_filters: Optional[List[str]] = None,
        workspace_filters: Optional[List[int]] = None,
    ) -> Dict[int, Dict[str, Any]]:
        """
        Get workspace facet counts for search results.

        Returns counts of all workspaces across matching chats, useful for building filter UI.

        Parameters
        ----
        query : str
            Search query
        tag_filters : List[str], optional
            If provided, only count workspaces for chats that have ALL these tags
        workspace_filters : List[int], optional
            If provided, only count workspaces matching these workspace IDs

        Returns
        ----
        Dict[int, Dict[str, Any]]
            Mapping of workspace_id -> {'count': int, 'resolved_path': str, 'workspace_hash': str}
        """
        cursor = self.conn.cursor()

        terms = query.strip().split()
        if not terms:
            return {}

        # Add prefix matching to last term
        fts_query = " ".join(terms[:-1] + [terms[-1] + "*"]) if terms else ""

        try:
            # Build base query to get matching chat IDs
            conditions = ["unified_fts MATCH ?"]
            params = [fts_query]

            # Add tag filters if provided
            if tag_filters:
                tag_placeholders = ",".join(["?"] * len(tag_filters))
                tag_subquery = f"""
                    SELECT chat_id 
                    FROM tags 
                    WHERE tag IN ({tag_placeholders})
                    GROUP BY chat_id
                    HAVING COUNT(DISTINCT tag) = ?
                """
                conditions.append(f"fts.chat_id IN ({tag_subquery})")
                params.extend(tag_filters)
                params.append(len(tag_filters))

            # Add workspace filters if provided
            if workspace_filters:
                workspace_placeholders = ",".join(["?"] * len(workspace_filters))
                conditions.append(f"c.workspace_id IN ({workspace_placeholders})")
                params.extend(workspace_filters)

            where_clause = " AND ".join(conditions)

            # Get matching chat IDs
            cursor.execute(
                f"""
                SELECT DISTINCT fts.chat_id, c.workspace_id
                FROM unified_fts fts
                INNER JOIN chats c ON fts.chat_id = c.id
                WHERE {where_clause}
            """,
                params,
            )

            matching_chats = cursor.fetchall()

            if not matching_chats:
                return {}

            # Get workspace IDs and their chat counts
            workspace_counts = {}
            for row in matching_chats:
                workspace_id = row[1]
                if workspace_id:
                    if workspace_id not in workspace_counts:
                        workspace_counts[workspace_id] = 0
                    workspace_counts[workspace_id] += 1

            if not workspace_counts:
                return {}

            # Get workspace details
            workspace_ids = list(workspace_counts.keys())
            placeholders = ",".join(["?"] * len(workspace_ids))
            cursor.execute(
                f"""
                SELECT id, workspace_hash, resolved_path
                FROM workspaces
                WHERE id IN ({placeholders})
            """,
                workspace_ids,
            )

            workspace_details = {
                row[0]: {"workspace_hash": row[1], "resolved_path": row[2]}
                for row in cursor.fetchall()
            }

            # Combine counts with details
            result = {}
            for workspace_id, count in workspace_counts.items():
                details = workspace_details.get(workspace_id, {})
                result[workspace_id] = {
                    "count": count,
                    "resolved_path": details.get("resolved_path", ""),
                    "workspace_hash": details.get("workspace_hash", ""),
                }

            return result

        except sqlite3.OperationalError as e:
            logger.debug("FTS workspace facet query error for '%s': %s", query, e)
            return {}

    def search_with_snippets_filtered(
        self,
        query: str,
        tag_filters: Optional[List[str]] = None,
        workspace_filters: Optional[List[int]] = None,
        project_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "relevance",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Full search with snippets, pagination, tag filtering, workspace filtering, and project filtering.

        Parameters
        ----
        query : str
            Search query
        tag_filters : List[str], optional
            Only return chats that have ALL of these tags
        workspace_filters : List[int], optional
            Only return chats from these workspace IDs
        project_id : int, optional
            Only return chats from workspaces in this project
        limit : int
            Maximum results per page
        offset : int
            Pagination offset
        sort_by : str
            Sort order: 'relevance' (BM25) or 'date' (newest first)

        Returns
        ----
        Tuple[List[Dict], int]
            (results with snippets, total count)
        """
        if not tag_filters and not workspace_filters and not project_id:
            # No filters, use existing method
            return self.search_with_snippets(query, limit, offset, sort_by)

        cursor = self.conn.cursor()

        terms = query.strip().split()
        if not terms:
            return [], 0

        # Add prefix matching to last term
        fts_query = " ".join(terms[:-1] + [terms[-1] + "*"]) if terms else ""

        # Clean query for title matching (used for boosting exact matches)
        clean_query = query.strip().lower()

        try:
            # Build filter conditions
            conditions = ["unified_fts MATCH ?"]
            params = [fts_query]

            # Build tag filter using subquery approach
            if tag_filters:
                tag_placeholders = ",".join(["?"] * len(tag_filters))
                tag_subquery = f"""
                    SELECT chat_id 
                    FROM tags 
                    WHERE tag IN ({tag_placeholders})
                    GROUP BY chat_id
                    HAVING COUNT(DISTINCT tag) = ?
                """
                conditions.append(f"fts.chat_id IN ({tag_subquery})")
                params.extend(tag_filters)
                params.append(len(tag_filters))

            # Build workspace filter
            if workspace_filters:
                workspace_placeholders = ",".join(["?"] * len(workspace_filters))
                conditions.append(f"c.workspace_id IN ({workspace_placeholders})")
                params.extend(workspace_filters)

            # Build project filter
            if project_id:
                conditions.append("w.project_id = ?")
                params.append(project_id)

            where_clause = " AND ".join(conditions)

            # Get total count first
            cursor.execute(
                f"""
                SELECT COUNT(DISTINCT fts.chat_id)
                FROM unified_fts fts
                INNER JOIN chats c ON fts.chat_id = c.id
                LEFT JOIN workspaces w ON c.workspace_id = w.id
                WHERE {where_clause}
            """,
                params,
            )

            total = cursor.fetchone()[0]

            # Determine sort order
            # For relevance sorting, we use a compound ORDER BY:
            # 1. Exact title match (highest priority)
            # 2. Title starts with query
            # 3. Title contains query
            # 4. BM25 weighted score
            if sort_by == "date":
                order_clause = "ORDER BY c.created_at DESC"
            else:
                order_clause = "ORDER BY title_boost, rank"

            # Build BM25 function call with column weights
            bm25_call = f"bm25(unified_fts, {', '.join(str(w) for w in self.BM25_WEIGHTS)})"

            # Get results with snippets
            cursor.execute(
                f"""
                SELECT 
                    fts.chat_id,
                    c.cursor_composer_id,
                    c.title,
                    c.mode,
                    c.created_at,
                    c.source,
                    c.messages_count,
                    w.workspace_hash,
                    w.resolved_path,
                    snippet(unified_fts, 3, '<mark>', '</mark>', '...', 64) as snippet,
                    {bm25_call} as rank,
                    CASE
                        WHEN LOWER(c.title) = ? THEN 0
                        WHEN LOWER(c.title) LIKE ? || '%' THEN 1
                        WHEN LOWER(c.title) LIKE '%' || ? || '%' THEN 2
                        ELSE 3
                    END as title_boost
                FROM unified_fts fts
                INNER JOIN chats c ON fts.chat_id = c.id
                LEFT JOIN workspaces w ON c.workspace_id = w.id
                WHERE {where_clause}
                {order_clause}
                LIMIT ? OFFSET ?
            """,
                [clean_query, clean_query, clean_query] + params + [limit, offset],
            )

            results = []
            chat_ids = []
            for row in cursor.fetchall():
                chat_id = row[0]
                chat_ids.append(chat_id)
                results.append(
                    {
                        "id": chat_id,
                        "composer_id": row[1],
                        "title": row[2] or "Untitled Chat",
                        "mode": row[3],
                        "created_at": row[4],
                        "source": row[5],
                        "messages_count": row[6] or 0,
                        "workspace_hash": row[7],
                        "workspace_path": row[8],
                        "snippet": row[9],
                        "rank": row[10],
                        "tags": [],
                    }
                )

            # Batch load tags
            if chat_ids:
                placeholders = ",".join(["?"] * len(chat_ids))
                cursor.execute(
                    f"""
                    SELECT chat_id, tag FROM tags 
                    WHERE chat_id IN ({placeholders})
                    ORDER BY chat_id, tag
                """,
                    chat_ids,
                )

                tags_by_chat = {}
                for row in cursor.fetchall():
                    chat_id, tag = row
                    if chat_id not in tags_by_chat:
                        tags_by_chat[chat_id] = []
                    tags_by_chat[chat_id].append(tag)

                for result in results:
                    result["tags"] = tags_by_chat.get(result["id"], [])

            return results, total

        except sqlite3.OperationalError as e:
            logger.debug("FTS filtered query error for '%s': %s", query, e)
            return [], 0

    def delete_empty_chats(self) -> int:
        """
        Delete all chats with messages_count = 0.

        Returns
        ----
        int
            Number of chats deleted
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM chats WHERE messages_count = 0")
        deleted = cursor.rowcount
        self.conn.commit()
        logger.info("Deleted %d empty chats", deleted)
        return deleted

    def rebuild_search_index(self):
        """
        Public method to rebuild the unified search index.

        Call this after bulk imports or if search seems inconsistent.
        """
        logger.info("Starting unified FTS index rebuild...")
        self._rebuild_unified_fts()
        logger.info("Unified FTS index rebuild complete")
