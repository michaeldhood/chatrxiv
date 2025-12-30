"""
Database layer for chat aggregation.

Provides SQLite database with FTS5 full-text search capabilities.
"""
import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import os

from src.core.models import Chat, Message, Workspace, ChatMode, MessageRole, CursorActivity
from src.core.config import get_default_db_path

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
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
        # Enable WAL mode for concurrent read/write access
        # This allows the daemon (writer) and web server (reader) to access DB simultaneously
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.fetchone()  # Consume the result
        
        cursor = self.conn.cursor()
        
        # Workspaces table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_hash TEXT UNIQUE NOT NULL,
                folder_uri TEXT,
                resolved_path TEXT,
                first_seen_at TEXT,
                last_seen_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
        if 'messages_count' not in columns:
            cursor.execute("ALTER TABLE chats ADD COLUMN messages_count INTEGER DEFAULT 0")
            logger.info("Added messages_count column to chats table")
        
        # Migration: Add model column if it doesn't exist
        if 'model' not in columns:
            cursor.execute("ALTER TABLE chats ADD COLUMN model TEXT")
            logger.info("Added model column to chats table")
        
        # Migration: Add estimated_cost column if it doesn't exist
        if 'estimated_cost' not in columns:
            cursor.execute("ALTER TABLE chats ADD COLUMN estimated_cost REAL")
            logger.info("Added estimated_cost column to chats table")
        
        # Cursor activity table for tracking usage/activity data
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cursor_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                model TEXT,
                workspace_hash TEXT,
                composer_id TEXT,
                chat_id INTEGER,
                tokens_input INTEGER,
                tokens_output INTEGER,
                cost REAL,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE SET NULL
            )
        """)
        
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
        if 'message_type' not in message_columns:
            cursor.execute("ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT 'response'")
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_composer_id ON chats(cursor_composer_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_workspace ON chats(workspace_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_created ON chats(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_updated ON chats(last_updated_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workspaces_hash ON workspaces(workspace_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON cursor_activity(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_chat ON cursor_activity(chat_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_model ON cursor_activity(model)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_model ON chats(model)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chats_cost ON chats(estimated_cost)")
        
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
        cursor.execute("SELECT id FROM workspaces WHERE workspace_hash = ?", (workspace.workspace_hash,))
        row = cursor.fetchone()
        
        if row:
            workspace_id = row[0]
            # Update
            cursor.execute("""
                UPDATE workspaces 
                SET folder_uri = ?, resolved_path = ?, last_seen_at = ?
                WHERE id = ?
            """, (
                workspace.folder_uri,
                workspace.resolved_path,
                datetime.now().isoformat() if workspace.last_seen_at else None,
                workspace_id
            ))
        else:
            # Insert
            cursor.execute("""
                INSERT INTO workspaces (workspace_hash, folder_uri, resolved_path, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                workspace.workspace_hash,
                workspace.folder_uri,
                workspace.resolved_path,
                workspace.first_seen_at.isoformat() if workspace.first_seen_at else datetime.now().isoformat(),
                workspace.last_seen_at.isoformat() if workspace.last_seen_at else datetime.now().isoformat(),
            ))
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
        cursor.execute("SELECT id FROM chats WHERE cursor_composer_id = ?", (chat.cursor_composer_id,))
        row = cursor.fetchone()
        
        # Calculate message count
        messages_count = len(chat.messages)
        
        if row:
            chat_id = row[0]
            # Update chat metadata
            cursor.execute("""
                UPDATE chats 
                SET workspace_id = ?, title = ?, mode = ?, created_at = ?, last_updated_at = ?, source = ?, messages_count = ?, model = ?, estimated_cost = ?
                WHERE id = ?
            """, (
                chat.workspace_id,
                chat.title or "",
                chat.mode.value,
                chat.created_at.isoformat() if chat.created_at else None,
                chat.last_updated_at.isoformat() if chat.last_updated_at else None,
                chat.source,
                messages_count,
                chat.model,
                chat.estimated_cost,
                chat_id
            ))
            # Delete old messages
            cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            cursor.execute("DELETE FROM chat_files WHERE chat_id = ?", (chat_id,))
        else:
            # Insert
            cursor.execute("""
                INSERT INTO chats (cursor_composer_id, workspace_id, title, mode, created_at, last_updated_at, source, messages_count, model, estimated_cost)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chat.cursor_composer_id,
                chat.workspace_id,
                chat.title or "",
                chat.mode.value,
                chat.created_at.isoformat() if chat.created_at else None,
                chat.last_updated_at.isoformat() if chat.last_updated_at else None,
                chat.source,
                messages_count,
                chat.model,
                chat.estimated_cost,
            ))
            chat_id = cursor.lastrowid
        
        # Insert messages
        for msg in chat.messages:
            cursor.execute("""
                INSERT INTO messages (chat_id, role, text, rich_text, created_at, cursor_bubble_id, raw_json, message_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chat_id,
                msg.role.value,
                msg.text or "",
                msg.rich_text or "",
                msg.created_at.isoformat() if msg.created_at else None,
                msg.cursor_bubble_id,
                json.dumps(msg.raw_json) if msg.raw_json else None,
                msg.message_type.value,
            ))
        
        # Insert relevant files
        for file_path in chat.relevant_files:
            cursor.execute("""
                INSERT OR IGNORE INTO chat_files (chat_id, path)
                VALUES (?, ?)
            """, (chat_id, file_path))
        
        self.conn.commit()
        
        # Update unified FTS index for instant search
        self._update_unified_fts(chat_id)
        
        return chat_id
    
    def search_chats(self, query: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
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
        
        cursor.execute("""
            SELECT DISTINCT c.id, c.cursor_composer_id, c.title, c.mode, c.created_at, c.source, c.messages_count,
                   w.workspace_hash, w.resolved_path
            FROM chats c
            LEFT JOIN workspaces w ON c.workspace_id = w.id
            INNER JOIN message_fts fts ON c.id = fts.chat_id
            WHERE message_fts MATCH ?
            ORDER BY c.created_at DESC
            LIMIT ? OFFSET ?
        """, (query, limit, offset))
        
        results = []
        chat_ids = []
        for row in cursor.fetchall():
            chat_id = row[0]
            chat_ids.append(chat_id)
            results.append({
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
            })
        
        # Load tags for all chats in batch
        if chat_ids:
            placeholders = ','.join(['?'] * len(chat_ids))
            cursor.execute(f"""
                SELECT chat_id, tag FROM tags 
                WHERE chat_id IN ({placeholders})
                ORDER BY chat_id, tag
            """, chat_ids)
            
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
        cursor.execute("""
            SELECT c.id, c.cursor_composer_id, c.workspace_id, c.title, c.mode, 
                   c.created_at, c.last_updated_at, c.source, c.messages_count,
                   c.model, c.estimated_cost,
                   w.workspace_hash, w.resolved_path
            FROM chats c
            LEFT JOIN workspaces w ON c.workspace_id = w.id
            WHERE c.id = ?
        """, (chat_id,))
        
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
            "model": row[9] if len(row) > 9 else None,
            "estimated_cost": row[10] if len(row) > 10 else None,
            "workspace_hash": row[11] if len(row) > 11 else None,
            "workspace_path": row[12] if len(row) > 12 else None,
            "messages": [],
            "files": [],
        }
        
        # Get messages
        cursor.execute("""
            SELECT role, text, rich_text, created_at, cursor_bubble_id, message_type
            FROM messages
            WHERE chat_id = ?
            ORDER BY created_at ASC
        """, (chat_id,))
        
        for msg_row in cursor.fetchall():
            chat_data["messages"].append({
                "role": msg_row[0],
                "text": msg_row[1],
                "rich_text": msg_row[2],
                "created_at": msg_row[3],
                "bubble_id": msg_row[4],
                "message_type": msg_row[5] if len(msg_row) > 5 else "response",  # Handle migration case
            })
        
        # Get files
        cursor.execute("SELECT path FROM chat_files WHERE chat_id = ?", (chat_id,))
        chat_data["files"] = [row[0] for row in cursor.fetchall()]
        
        # Get tags
        cursor.execute("SELECT tag FROM tags WHERE chat_id = ? ORDER BY tag", (chat_id,))
        chat_data["tags"] = [row[0] for row in cursor.fetchall()]
        
        return chat_data
    
    def count_chats(self, workspace_id: Optional[int] = None, empty_filter: Optional[str] = None) -> int:
        """
        Count total chats, optionally filtered by workspace and empty status.
        
        Parameters
        ----
        workspace_id : int, optional
            Filter by workspace
        empty_filter : str, optional
            Filter by empty status: 'empty' (messages_count = 0), 'non_empty' (messages_count > 0), or None (all)
            
        Returns
        ----
        int
            Total count of chats
        """
        cursor = self.conn.cursor()
        
        conditions = []
        params = []
        
        if workspace_id:
            conditions.append("workspace_id = ?")
            params.append(workspace_id)
        
        if empty_filter == 'empty':
            conditions.append("messages_count = 0")
        elif empty_filter == 'non_empty':
            conditions.append("messages_count > 0")
        
        query = "SELECT COUNT(*) FROM chats"
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
        
        cursor.execute("""
            SELECT COUNT(DISTINCT c.id)
            FROM chats c
            INNER JOIN message_fts fts ON c.id = fts.chat_id
            WHERE message_fts MATCH ?
        """, (query,))
        
        return cursor.fetchone()[0]
    
    def list_chats(self, workspace_id: Optional[int] = None, limit: int = 100, offset: int = 0, 
                   empty_filter: Optional[str] = None) -> List[Dict[str, Any]]:
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
        
        if empty_filter == 'empty':
            conditions.append("c.messages_count = 0")
        elif empty_filter == 'non_empty':
            conditions.append("c.messages_count > 0")
        
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        
        query = f"""
            SELECT c.id, c.cursor_composer_id, c.title, c.mode, c.created_at, c.source, c.messages_count,
                   w.workspace_hash, w.resolved_path
            FROM chats c
            LEFT JOIN workspaces w ON c.workspace_id = w.id
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
            results.append({
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
            })
        
        # Load tags for all chats in batch
        if chat_ids:
            placeholders = ','.join(['?'] * len(chat_ids))
            cursor.execute(f"""
                SELECT chat_id, tag FROM tags 
                WHERE chat_id IN ({placeholders})
                ORDER BY chat_id, tag
            """, chat_ids)
            
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
        cursor.execute("""
            SELECT last_run_at, last_processed_timestamp, last_composer_id,
                   stats_ingested, stats_skipped, stats_errors
            FROM ingestion_state
            WHERE source = ?
        """, (source,))
        
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
    
    def update_ingestion_state(self, source: str, last_run_at: Optional[datetime] = None,
                              last_processed_timestamp: Optional[str] = None,
                              last_composer_id: Optional[str] = None,
                              stats: Optional[Dict[str, int]] = None):
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
                    params
                )
        else:
            # Insert
            cursor.execute("""
                INSERT INTO ingestion_state 
                (source, last_run_at, last_processed_timestamp, last_composer_id, 
                 stats_ingested, stats_skipped, stats_errors)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                source,
                last_run_at.isoformat() if last_run_at else None,
                last_processed_timestamp,
                last_composer_id,
                stats.get("ingested", 0) if stats else 0,
                stats.get("skipped", 0) if stats else 0,
                stats.get("errors", 0) if stats else 0,
            ))
        
        self.conn.commit()
    
    def get_chats_updated_since(self, timestamp: datetime, source: str = "cursor") -> List[str]:
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
        cursor.execute("""
            SELECT cursor_composer_id
            FROM chats
            WHERE source = ? AND last_updated_at > ?
            ORDER BY last_updated_at ASC
        """, (source, timestamp.isoformat()))
        
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
        cursor.execute("""
            SELECT id, cursor_composer_id, last_updated_at, source
            FROM chats WHERE cursor_composer_id = ?
        """, (composer_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "cursor_composer_id": row[1],
            "last_updated_at": row[2],
            "source": row[3]
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
                    (chat_id, tag)
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
            [(chat_id, tag) for tag in tags]
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
        cursor.execute("SELECT tag FROM tags WHERE chat_id = ? ORDER BY tag", (chat_id,))
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
        cursor.execute("SELECT tag, COUNT(*) as count FROM tags GROUP BY tag ORDER BY count DESC")
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
            cursor.execute("""
                SELECT GROUP_CONCAT(text, ' ') 
                FROM messages 
                WHERE chat_id = ?
            """, (chat_id,))
            message_text = cursor.fetchone()[0] or ""
            
            # Get tags
            cursor.execute("""
                SELECT GROUP_CONCAT(tag, ' ')
                FROM tags
                WHERE chat_id = ?
            """, (chat_id,))
            tags = cursor.fetchone()[0] or ""
            
            # Get files
            cursor.execute("""
                SELECT GROUP_CONCAT(path, ' ')
                FROM chat_files
                WHERE chat_id = ?
            """, (chat_id,))
            files = cursor.fetchone()[0] or ""
            
            # Insert into unified FTS
            cursor.execute("""
                INSERT INTO unified_fts (chat_id, content_type, title, message_text, tags, files)
                VALUES (?, 'chat', ?, ?, ?, ?)
            """, (chat_id, title or "", message_text, tags, files))
        
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
        cursor.execute("""
            SELECT GROUP_CONCAT(text, ' ')
            FROM messages
            WHERE chat_id = ?
        """, (chat_id,))
        message_text = cursor.fetchone()[0] or ""
        
        # Get tags
        cursor.execute("""
            SELECT GROUP_CONCAT(tag, ' ')
            FROM tags
            WHERE chat_id = ?
        """, (chat_id,))
        tags = cursor.fetchone()[0] or ""
        
        # Get files
        cursor.execute("""
            SELECT GROUP_CONCAT(path, ' ')
            FROM chat_files
            WHERE chat_id = ?
        """, (chat_id,))
        files = cursor.fetchone()[0] or ""
        
        # Insert updated entry
        cursor.execute("""
            INSERT INTO unified_fts (chat_id, content_type, title, message_text, tags, files)
            VALUES (?, 'chat', ?, ?, ?, ?)
        """, (chat_id, title, message_text, tags, files))
        
        self.conn.commit()
    
    def instant_search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
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
        fts_query = ' '.join(terms[:-1] + [terms[-1] + '*']) if terms else ''
        
        try:
            # Search with snippet generation
            # snippet() function: table, column_idx, start_mark, end_mark, ellipsis, max_tokens
            cursor.execute("""
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
                    bm25(unified_fts) as rank
                FROM unified_fts fts
                INNER JOIN chats c ON fts.chat_id = c.id
                LEFT JOIN workspaces w ON c.workspace_id = w.id
                WHERE unified_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, limit))
            
            results = []
            chat_ids = []
            for row in cursor.fetchall():
                chat_id = row[0]
                chat_ids.append(chat_id)
                results.append({
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
                })
            
            # Batch load tags
            if chat_ids:
                placeholders = ','.join(['?'] * len(chat_ids))
                cursor.execute(f"""
                    SELECT chat_id, tag FROM tags 
                    WHERE chat_id IN ({placeholders})
                    ORDER BY chat_id, tag
                """, chat_ids)
                
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
    
    def search_with_snippets(self, query: str, limit: int = 50, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
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
        fts_query = ' '.join(terms[:-1] + [terms[-1] + '*']) if terms else ''
        
        try:
            # Get total count first
            cursor.execute("""
                SELECT COUNT(DISTINCT chat_id)
                FROM unified_fts
                WHERE unified_fts MATCH ?
            """, (fts_query,))
            total = cursor.fetchone()[0]
            
            # Get results with snippets
            cursor.execute("""
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
                    bm25(unified_fts) as rank
                FROM unified_fts fts
                INNER JOIN chats c ON fts.chat_id = c.id
                LEFT JOIN workspaces w ON c.workspace_id = w.id
                WHERE unified_fts MATCH ?
                ORDER BY rank
                LIMIT ? OFFSET ?
            """, (fts_query, limit, offset))
            
            results = []
            chat_ids = []
            for row in cursor.fetchall():
                chat_id = row[0]
                chat_ids.append(chat_id)
                results.append({
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
                })
            
            # Batch load tags
            if chat_ids:
                placeholders = ','.join(['?'] * len(chat_ids))
                cursor.execute(f"""
                    SELECT chat_id, tag FROM tags 
                    WHERE chat_id IN ({placeholders})
                    ORDER BY chat_id, tag
                """, chat_ids)
                
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
        self, query: str, tag_filters: Optional[List[str]] = None
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
        fts_query = ' '.join(terms[:-1] + [terms[-1] + '*']) if terms else ''
        
        try:
            if tag_filters:
                # Get chat IDs matching both FTS query AND all tag filters
                placeholders = ','.join(['?'] * len(tag_filters))
                cursor.execute(f"""
                    SELECT DISTINCT fts.chat_id
                    FROM unified_fts fts
                    INNER JOIN tags t ON fts.chat_id = t.chat_id
                    WHERE unified_fts MATCH ?
                    AND t.tag IN ({placeholders})
                    GROUP BY fts.chat_id
                    HAVING COUNT(DISTINCT t.tag) = ?
                """, (fts_query, *tag_filters, len(tag_filters)))
            else:
                cursor.execute("""
                    SELECT DISTINCT chat_id
                    FROM unified_fts
                    WHERE unified_fts MATCH ?
                """, (fts_query,))
            
            matching_chat_ids = [row[0] for row in cursor.fetchall()]
            
            if not matching_chat_ids:
                return {}
            
            # Get tag counts for matching chats
            placeholders = ','.join(['?'] * len(matching_chat_ids))
            cursor.execute(f"""
                SELECT tag, COUNT(*) as cnt
                FROM tags
                WHERE chat_id IN ({placeholders})
                GROUP BY tag
                ORDER BY cnt DESC, tag ASC
            """, matching_chat_ids)
            
            return {row[0]: row[1] for row in cursor.fetchall()}
            
        except sqlite3.OperationalError as e:
            logger.debug("FTS facet query error for '%s': %s", query, e)
            return {}
    
    def search_with_snippets_filtered(
        self, 
        query: str, 
        tag_filters: Optional[List[str]] = None,
        limit: int = 50, 
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Full search with snippets, pagination, and tag filtering.
        
        Parameters
        ----
        query : str
            Search query
        tag_filters : List[str], optional
            Only return chats that have ALL of these tags
        limit : int
            Maximum results per page
        offset : int
            Pagination offset
            
        Returns
        ----
        Tuple[List[Dict], int]
            (results with snippets, total count)
        """
        if not tag_filters:
            # No filters, use existing method
            return self.search_with_snippets(query, limit, offset)
        
        cursor = self.conn.cursor()
        
        terms = query.strip().split()
        if not terms:
            return [], 0
        
        # Add prefix matching to last term
        fts_query = ' '.join(terms[:-1] + [terms[-1] + '*']) if terms else ''
        
        try:
            # Build tag filter using subquery approach
            # Find chats that have ALL specified tags
            tag_placeholders = ','.join(['?'] * len(tag_filters))
            
            # Subquery to get chat_ids that have all required tags
            tag_subquery = f"""
                SELECT chat_id 
                FROM tags 
                WHERE tag IN ({tag_placeholders})
                GROUP BY chat_id
                HAVING COUNT(DISTINCT tag) = ?
            """
            
            # Get total count first
            cursor.execute(f"""
                SELECT COUNT(DISTINCT fts.chat_id)
                FROM unified_fts fts
                WHERE unified_fts MATCH ?
                AND fts.chat_id IN ({tag_subquery})
            """, (fts_query, *tag_filters, len(tag_filters)))
            
            total = cursor.fetchone()[0]
            
            # Get results with snippets
            cursor.execute(f"""
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
                    bm25(unified_fts) as rank
                FROM unified_fts fts
                INNER JOIN chats c ON fts.chat_id = c.id
                LEFT JOIN workspaces w ON c.workspace_id = w.id
                WHERE unified_fts MATCH ?
                AND fts.chat_id IN ({tag_subquery})
                ORDER BY rank
                LIMIT ? OFFSET ?
            """, (fts_query, *tag_filters, len(tag_filters), limit, offset))
            
            results = []
            chat_ids = []
            for row in cursor.fetchall():
                chat_id = row[0]
                chat_ids.append(chat_id)
                results.append({
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
                })
            
            # Batch load tags
            if chat_ids:
                placeholders = ','.join(['?'] * len(chat_ids))
                cursor.execute(f"""
                    SELECT chat_id, tag FROM tags 
                    WHERE chat_id IN ({placeholders})
                    ORDER BY chat_id, tag
                """, chat_ids)
                
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
    
    def upsert_activity(self, activity: CursorActivity) -> int:
        """
        Insert or update a cursor activity record.
        
        Parameters
        ----
        activity : CursorActivity
            Activity to upsert
            
        Returns
        ----
        int
            Activity ID
        """
        cursor = self.conn.cursor()
        
        # If chat_id is None but composer_id is provided, try to find chat_id
        if activity.chat_id is None and activity.composer_id:
            cursor.execute("SELECT id FROM chats WHERE cursor_composer_id = ?", (activity.composer_id,))
            row = cursor.fetchone()
            if row:
                activity.chat_id = row[0]
        
        cursor.execute("""
            INSERT INTO cursor_activity 
            (timestamp, activity_type, model, workspace_hash, composer_id, chat_id, 
             tokens_input, tokens_output, cost, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            activity.timestamp.isoformat() if activity.timestamp else None,
            activity.activity_type,
            activity.model,
            activity.workspace_hash,
            activity.composer_id,
            activity.chat_id,
            activity.tokens_input,
            activity.tokens_output,
            activity.cost,
            json.dumps(activity.metadata) if activity.metadata else None,
        ))
        
        activity_id = cursor.lastrowid
        self.conn.commit()
        return activity_id
    
    def get_activity_for_chat(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        Get all activity records for a specific chat.
        
        Parameters
        ----
        chat_id : int
            Chat ID
            
        Returns
        ----
        List[Dict[str, Any]]
            List of activity records
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, activity_type, model, tokens_input, tokens_output, cost, metadata
            FROM cursor_activity
            WHERE chat_id = ?
            ORDER BY timestamp ASC
        """, (chat_id,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "timestamp": row[1],
                "activity_type": row[2],
                "model": row[3],
                "tokens_input": row[4],
                "tokens_output": row[5],
                "cost": row[6],
                "metadata": json.loads(row[7]) if row[7] else None,
            })
        return results
    
    def get_activity_summary(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get summary statistics for cursor activity.
        
        Parameters
        ----
        start_date : str, optional
            Start date (ISO format)
        end_date : str, optional
            End date (ISO format)
            
        Returns
        ----
        Dict[str, Any]
            Summary statistics
        """
        cursor = self.conn.cursor()
        
        conditions = []
        params = []
        
        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)
        
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        
        # Total cost
        cursor.execute(f"""
            SELECT COALESCE(SUM(cost), 0) FROM cursor_activity {where_clause}
        """, params)
        total_cost = cursor.fetchone()[0] or 0.0
        
        # Total tokens
        cursor.execute(f"""
            SELECT COALESCE(SUM(tokens_input), 0), COALESCE(SUM(tokens_output), 0)
            FROM cursor_activity {where_clause}
        """, params)
        row = cursor.fetchone()
        total_input_tokens = row[0] or 0
        total_output_tokens = row[1] or 0
        
        # Activity count by type
        cursor.execute(f"""
            SELECT activity_type, COUNT(*) 
            FROM cursor_activity {where_clause}
            GROUP BY activity_type
        """, params)
        activity_by_type = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Cost by model
        cursor.execute(f"""
            SELECT model, COALESCE(SUM(cost), 0), COUNT(*)
            FROM cursor_activity {where_clause}
            WHERE model IS NOT NULL
            GROUP BY model
        """, params)
        cost_by_model = {row[0]: {"cost": row[1] or 0.0, "count": row[2]} for row in cursor.fetchall()}
        
        return {
            "total_cost": total_cost,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "activity_by_type": activity_by_type,
            "cost_by_model": cost_by_model,
        }

