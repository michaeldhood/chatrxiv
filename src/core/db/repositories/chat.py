"""
Chat repository for database operations on chats and messages.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.models import Chat, MessageType
from .base import BaseRepository


class ChatRepository(BaseRepository):
    """
    Repository for chat CRUD operations.

    Handles chat creation, retrieval, listing, and search operations.
    """

    def __init__(self, conn, fts_manager=None):
        """
        Initialize chat repository.

        Parameters
        ----------
        conn : DatabaseConnection
            Database connection to use
        fts_manager : FTSManager, optional
            FTS manager for updating search index
        """
        super().__init__(conn)
        self._fts = fts_manager

    def set_fts_manager(self, fts_manager) -> None:
        """Set the FTS manager for updating search index."""
        self._fts = fts_manager

    def upsert(self, chat: Chat) -> int:
        """
        Insert or update a chat and its messages.

        Parameters
        ----------
        chat : Chat
            Chat to upsert

        Returns
        -------
        int
            Chat ID
        """
        cursor = self.cursor()

        # Check if exists
        cursor.execute(
            "SELECT id FROM chats WHERE cursor_composer_id = ?",
            (chat.cursor_composer_id,),
        )
        row = cursor.fetchone()

        # Calculate message counts
        messages_count = len(chat.messages)
        thinking_count = sum(
            1 for msg in chat.messages if msg.message_type == MessageType.THINKING
        )

        if row:
            chat_id = row[0]
            # Update chat metadata
            cursor.execute(
                """
                UPDATE chats
                SET workspace_id = ?, title = ?, mode = ?, created_at = ?,
                    last_updated_at = ?, source = ?, messages_count = ?,
                    model = ?, estimated_cost = ?, thinking_count = ?
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
                    chat.model,
                    chat.estimated_cost,
                    thinking_count,
                    chat_id,
                ),
            )
            # Delete old messages and files
            cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            cursor.execute("DELETE FROM chat_files WHERE chat_id = ?", (chat_id,))
        else:
            # Insert
            cursor.execute(
                """
                INSERT INTO chats (cursor_composer_id, workspace_id, title, mode,
                    created_at, last_updated_at, source, messages_count, model,
                    estimated_cost, thinking_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    chat.model,
                    chat.estimated_cost,
                    thinking_count,
                ),
            )
            chat_id = cursor.lastrowid

        # Insert messages
        for msg in chat.messages:
            cursor.execute(
                """
                INSERT INTO messages (chat_id, role, text, rich_text, created_at,
                    cursor_bubble_id, raw_json, message_type)
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

        self.commit()

        # Update unified FTS index for instant search
        if self._fts:
            self._fts.update_chat_index(chat_id)

        return chat_id

    def get(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a chat with all its messages.

        Parameters
        ----------
        chat_id : int
            Chat ID

        Returns
        -------
        Optional[Dict[str, Any]]
            Chat data with messages, or None if not found
        """
        cursor = self.cursor()

        # Get chat - explicitly select columns to handle schema migration
        cursor.execute(
            """
            SELECT c.id, c.cursor_composer_id, c.workspace_id, c.title, c.mode,
                   c.created_at, c.last_updated_at, c.source, c.messages_count,
                   c.summary, c.model, c.estimated_cost, c.thinking_count,
                   w.workspace_hash, w.resolved_path
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
            "messages_count": row[8] if len(row) > 8 else 0,
            "summary": row[9] if len(row) > 9 else None,
            "model": row[10] if len(row) > 10 else None,
            "estimated_cost": row[11] if len(row) > 11 else None,
            "thinking_count": row[12] if len(row) > 12 else 0,
            "workspace_hash": row[13] if len(row) > 13 else None,
            "workspace_path": row[14] if len(row) > 14 else None,
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
                    "message_type": msg_row[5] if len(msg_row) > 5 else "response",
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

    def get_by_composer_id(self, composer_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a chat by its Cursor composer ID.

        Parameters
        ----------
        composer_id : str
            Cursor composer ID

        Returns
        -------
        Optional[Dict[str, Any]]
            Minimal chat record or None if not found
        """
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT id, cursor_composer_id, title, last_updated_at
            FROM chats
            WHERE cursor_composer_id = ?
            """,
            (composer_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row[0],
            "composer_id": row[1],
            "title": row[2],
            "last_updated_at": row[3],
        }

    def update_summary(self, chat_id: int, summary: str) -> None:
        """
        Update the summary for a chat.

        Parameters
        ----------
        chat_id : int
            Chat ID
        summary : str
            Summary text to store
        """
        cursor = self.cursor()
        cursor.execute(
            "UPDATE chats SET summary = ? WHERE id = ?",
            (summary, chat_id),
        )
        self.commit()

    def list(
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
        ----------
        workspace_id : int, optional
            Filter by workspace
        limit : int
            Maximum number of results
        offset : int
            Offset for pagination
        empty_filter : str, optional
            Filter by empty status: 'empty', 'non_empty', or None
        project_id : int, optional
            Filter by project

        Returns
        -------
        List[Dict[str, Any]]
            List of chats
        """
        cursor = self.cursor()

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

        join_type = "INNER JOIN" if project_id else "LEFT JOIN"

        query = f"""
            SELECT c.id, c.cursor_composer_id, c.title, c.mode, c.created_at,
                   c.source, c.messages_count, w.workspace_hash, w.resolved_path
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

    def count(
        self,
        workspace_id: Optional[int] = None,
        empty_filter: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> int:
        """
        Count total chats with optional filtering.

        Parameters
        ----------
        workspace_id : int, optional
            Filter by workspace
        empty_filter : str, optional
            Filter by empty status
        project_id : int, optional
            Filter by project

        Returns
        -------
        int
            Total count of chats
        """
        cursor = self.cursor()

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

    def delete_empty(self) -> int:
        """
        Delete all chats with zero messages.

        Returns
        -------
        int
            Number of chats deleted
        """
        cursor = self.cursor()
        cursor.execute("SELECT COUNT(*) FROM chats WHERE messages_count = 0")
        count = cursor.fetchone()[0]

        cursor.execute("DELETE FROM chats WHERE messages_count = 0")
        self.commit()
        return count

    def get_filter_options(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all available filter options for the UI.

        Returns
        -------
        Dict[str, List[Dict[str, Any]]]
            Dictionary with 'sources' and 'modes' keys
        """
        cursor = self.cursor()

        cursor.execute(
            """
            SELECT source, COUNT(*) as count
            FROM chats
            WHERE source IS NOT NULL AND source != ''
            GROUP BY source
            ORDER BY count DESC
        """
        )
        sources = [{"value": row[0], "count": row[1]} for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT mode, COUNT(*) as count
            FROM chats
            WHERE mode IS NOT NULL AND mode != ''
            GROUP BY mode
            ORDER BY count DESC
        """
        )
        modes = [{"value": row[0], "count": row[1]} for row in cursor.fetchall()]

        return {"sources": sources, "modes": modes}

    def get_last_updated_at(self) -> Optional[datetime]:
        """
        Get the most recent chat update timestamp.

        Returns
        -------
        Optional[datetime]
            Most recent update timestamp or None if no chats
        """
        cursor = self.cursor()
        cursor.execute("SELECT MAX(last_updated_at) FROM chats")
        row = cursor.fetchone()
        if row and row[0]:
            return datetime.fromisoformat(row[0])
        return None
