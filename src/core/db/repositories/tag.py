"""
Tag repository for database operations on tags.
"""

import sqlite3
from typing import Any, Dict, List

from .base import BaseRepository


class TagRepository(BaseRepository):
    """
    Repository for tag operations.

    Handles adding, removing, and querying tags on chats.
    """

    def add(self, chat_id: int, tags: List[str]) -> None:
        """
        Add tags to a chat.

        Parameters
        ----------
        chat_id : int
            Chat ID
        tags : List[str]
            List of tags to add
        """
        cursor = self.cursor()
        for tag in tags:
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO tags (chat_id, tag) VALUES (?, ?)",
                    (chat_id, tag),
                )
            except sqlite3.IntegrityError:
                pass
        self.commit()

    def remove(self, chat_id: int, tags: List[str]) -> None:
        """
        Remove tags from a chat.

        Parameters
        ----------
        chat_id : int
            Chat ID
        tags : List[str]
            List of tags to remove
        """
        cursor = self.cursor()
        cursor.executemany(
            "DELETE FROM tags WHERE chat_id = ? AND tag = ?",
            [(chat_id, tag) for tag in tags],
        )
        self.commit()

    def get_for_chat(self, chat_id: int) -> List[str]:
        """
        Get all tags for a chat.

        Parameters
        ----------
        chat_id : int
            Chat ID

        Returns
        -------
        List[str]
            List of tags
        """
        cursor = self.cursor()
        cursor.execute(
            "SELECT tag FROM tags WHERE chat_id = ? ORDER BY tag", (chat_id,)
        )
        return [row[0] for row in cursor.fetchall()]

    def get_all(self) -> Dict[str, int]:
        """
        Get all unique tags with their frequency.

        Returns
        -------
        Dict[str, int]
            Dictionary mapping tags to their occurrence count
        """
        cursor = self.cursor()
        cursor.execute(
            "SELECT tag, COUNT(*) as count FROM tags GROUP BY tag ORDER BY count DESC"
        )
        return {row[0]: row[1] for row in cursor.fetchall()}

    def find_chats(self, tag: str) -> List[int]:
        """
        Find all chat IDs with a specific tag.

        Parameters
        ----------
        tag : str
            Tag to search for (supports SQL LIKE wildcards: %)

        Returns
        -------
        List[int]
            List of chat IDs
        """
        cursor = self.cursor()
        cursor.execute("SELECT DISTINCT chat_id FROM tags WHERE tag LIKE ?", (tag,))
        return [row[0] for row in cursor.fetchall()]

    def get_chat_files(self, chat_id: int) -> List[str]:
        """
        Get all file paths associated with a chat.

        Parameters
        ----------
        chat_id : int
            Chat ID

        Returns
        -------
        List[str]
            List of file paths
        """
        cursor = self.cursor()
        cursor.execute("SELECT path FROM chat_files WHERE chat_id = ?", (chat_id,))
        return [row[0] for row in cursor.fetchall()]
