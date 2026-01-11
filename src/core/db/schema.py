"""
Database schema management for the chat aggregation system.

Provides SchemaManager class that handles table creation, migrations,
indexes, and FTS5 virtual tables.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SchemaManager:
    """
    Manages database schema creation and migrations.

    This class handles:
    - Initial table creation
    - Column migrations for existing tables
    - FTS5 virtual table setup
    - Index creation
    - Trigger setup for FTS sync
    """

    def __init__(self, conn: "DatabaseConnection"):
        """
        Initialize schema manager.

        Parameters
        ----------
        conn : DatabaseConnection
            Database connection to use for schema operations.
        """
        self._conn = conn

    def ensure(self) -> None:
        """Ensure all database schema exists and is up to date."""
        cursor = self._conn.cursor()

        # Create core tables
        self._create_projects_table(cursor)
        self._create_workspaces_table(cursor)
        self._create_chats_table(cursor)
        self._create_messages_table(cursor)
        self._create_chat_files_table(cursor)
        self._create_tags_table(cursor)
        self._create_plans_table(cursor)
        self._create_chat_plans_table(cursor)
        self._create_cursor_activity_table(cursor)
        self._create_ingestion_state_table(cursor)

        # Apply migrations
        self._migrate_chats_table(cursor)
        self._migrate_workspaces_table(cursor)
        self._migrate_messages_table(cursor)

        # Create FTS tables and triggers
        self._create_message_fts(cursor)
        self._create_unified_fts(cursor)
        self._create_fts_triggers(cursor)

        # Create indexes
        self._create_indexes(cursor)

        # Check if unified FTS needs rebuilding
        self._check_unified_fts_migration(cursor)

        self._conn.commit()
        logger.info("Database schema initialized at %s", self._conn.db_path)

    def _create_projects_table(self, cursor) -> None:
        """Create projects table for grouping workspaces."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _create_workspaces_table(self, cursor) -> None:
        """Create workspaces table."""
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

    def _create_chats_table(self, cursor) -> None:
        """Create chats table."""
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

    def _create_messages_table(self, cursor) -> None:
        """Create messages table."""
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

    def _create_chat_files_table(self, cursor) -> None:
        """Create chat_files table for relevant files per chat."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_files (
                chat_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                PRIMARY KEY (chat_id, path),
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)

    def _create_tags_table(self, cursor) -> None:
        """Create tags table."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                chat_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (chat_id, tag),
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)

    def _create_plans_table(self, cursor) -> None:
        """Create plans table for plan metadata."""
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

    def _create_chat_plans_table(self, cursor) -> None:
        """Create junction table for chat-plan relationships."""
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

    def _create_cursor_activity_table(self, cursor) -> None:
        """Create cursor_activity table for usage tracking."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cursor_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                kind TEXT NOT NULL,
                model TEXT,
                max_mode INTEGER,
                input_tokens_with_cache INTEGER,
                input_tokens_no_cache INTEGER,
                cache_read_tokens INTEGER,
                output_tokens INTEGER,
                total_tokens INTEGER,
                cost REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, model, kind)
            )
        """)

    def _create_ingestion_state_table(self, cursor) -> None:
        """Create ingestion_state table for tracking incremental ingestion."""
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

    def _migrate_chats_table(self, cursor) -> None:
        """Apply migrations for chats table."""
        cursor.execute("PRAGMA table_info(chats)")
        columns = [row[1] for row in cursor.fetchall()]

        if "messages_count" not in columns:
            cursor.execute(
                "ALTER TABLE chats ADD COLUMN messages_count INTEGER DEFAULT 0"
            )
            logger.info("Added messages_count column to chats table")

        if "summary" not in columns:
            cursor.execute("ALTER TABLE chats ADD COLUMN summary TEXT")
            logger.info("Added summary column to chats table")

        if "model" not in columns:
            cursor.execute("ALTER TABLE chats ADD COLUMN model TEXT")
            logger.info("Added model column to chats table")

        if "estimated_cost" not in columns:
            cursor.execute("ALTER TABLE chats ADD COLUMN estimated_cost REAL")
            logger.info("Added estimated_cost column to chats table")

    def _migrate_workspaces_table(self, cursor) -> None:
        """Apply migrations for workspaces table."""
        cursor.execute("PRAGMA table_info(workspaces)")
        columns = [row[1] for row in cursor.fetchall()]

        if "project_id" not in columns:
            cursor.execute(
                "ALTER TABLE workspaces ADD COLUMN project_id INTEGER REFERENCES projects(id)"
            )
            logger.info("Added project_id column to workspaces table")

    def _migrate_messages_table(self, cursor) -> None:
        """Apply migrations for messages table."""
        cursor.execute("PRAGMA table_info(messages)")
        columns = [row[1] for row in cursor.fetchall()]

        if "message_type" not in columns:
            cursor.execute(
                "ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT 'response'"
            )
            logger.info("Added message_type column to messages table")

    def _create_message_fts(self, cursor) -> None:
        """Create FTS5 virtual table for message search."""
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
                chat_id,
                text,
                rich_text,
                content='messages',
                content_rowid='id'
            )
        """)

    def _create_unified_fts(self, cursor) -> None:
        """Create unified FTS5 table for Obsidian-like search."""
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

    def _create_fts_triggers(self, cursor) -> None:
        """Create triggers to keep FTS in sync with messages table."""
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

    def _create_indexes(self, cursor) -> None:
        """Create performance indexes."""
        indexes = [
            ("idx_chats_composer_id", "chats", "cursor_composer_id"),
            ("idx_chats_workspace", "chats", "workspace_id"),
            ("idx_chats_created", "chats", "created_at"),
            ("idx_chats_updated", "chats", "last_updated_at"),
            ("idx_chats_model", "chats", "model"),
            ("idx_chats_cost", "chats", "estimated_cost"),
            ("idx_messages_chat", "messages", "chat_id"),
            ("idx_messages_created", "messages", "created_at"),
            ("idx_workspaces_hash", "workspaces", "workspace_hash"),
            ("idx_workspaces_project", "workspaces", "project_id"),
            ("idx_plans_plan_id", "plans", "plan_id"),
            ("idx_chat_plans_chat", "chat_plans", "chat_id"),
            ("idx_chat_plans_plan", "chat_plans", "plan_id"),
            ("idx_activity_date", "cursor_activity", "date"),
            ("idx_activity_model", "cursor_activity", "model"),
        ]

        for idx_name, table, column in indexes:
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})"
            )

    def _check_unified_fts_migration(self, cursor) -> None:
        """Check if unified FTS needs to be rebuilt for existing databases."""
        cursor.execute("SELECT COUNT(*) FROM unified_fts")
        unified_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM chats")
        chat_count = cursor.fetchone()[0]

        if chat_count > 0 and unified_count == 0:
            logger.info("Rebuilding unified FTS index for %d chats...", chat_count)
            self._rebuild_unified_fts(cursor)

    def _rebuild_unified_fts(self, cursor) -> None:
        """Rebuild the unified FTS index from scratch."""
        # Clear existing FTS data
        cursor.execute("DELETE FROM unified_fts")

        # Get all chats with their content
        cursor.execute("""
            SELECT
                c.id,
                c.title,
                GROUP_CONCAT(DISTINCT m.text, ' ') as message_text,
                GROUP_CONCAT(DISTINCT t.tag, ' ') as tags,
                GROUP_CONCAT(DISTINCT cf.path, ' ') as files
            FROM chats c
            LEFT JOIN messages m ON c.id = m.chat_id
            LEFT JOIN tags t ON c.id = t.chat_id
            LEFT JOIN chat_files cf ON c.id = cf.chat_id
            GROUP BY c.id
        """)

        rows = cursor.fetchall()
        for row in rows:
            cursor.execute(
                """
                INSERT INTO unified_fts (chat_id, content_type, title, message_text, tags, files)
                VALUES (?, 'chat', ?, ?, ?, ?)
                """,
                (row[0], row[1] or "", row[2] or "", row[3] or "", row[4] or ""),
            )

        logger.info("Rebuilt unified FTS index with %d entries", len(rows))
