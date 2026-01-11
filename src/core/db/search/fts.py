"""
FTS5 index management for unified full-text search.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..connection import DatabaseConnection

logger = logging.getLogger(__name__)


class FTSManager:
    """
    Manages the unified FTS5 index.

    Handles rebuilding and updating the full-text search index
    for Obsidian-like search across chats, messages, tags, and files.
    """

    def __init__(self, conn: "DatabaseConnection"):
        """
        Initialize FTS manager.

        Parameters
        ----------
        conn : DatabaseConnection
            Database connection
        """
        self._conn = conn

    def cursor(self):
        """Get a database cursor."""
        return self._conn.cursor()

    def commit(self):
        """Commit the current transaction."""
        self._conn.commit()

    def rebuild_unified_index(self) -> int:
        """
        Rebuild the unified FTS index from all existing data.

        Returns
        -------
        int
            Number of chats indexed
        """
        cursor = self.cursor()

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

        self.commit()
        logger.info("Rebuilt unified FTS index with %d chats", len(chats))
        return len(chats)

    def update_chat_index(self, chat_id: int) -> None:
        """
        Update unified FTS entry for a specific chat.

        Parameters
        ----------
        chat_id : int
            Chat database ID to update
        """
        cursor = self.cursor()

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

        self.commit()
