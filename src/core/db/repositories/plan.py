"""
Plan repository for database operations on plans.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseRepository


class PlanRepository(BaseRepository):
    """
    Repository for plan operations.

    Handles plan metadata and chat-plan relationships.
    """

    def upsert(
        self,
        plan_id: str,
        name: str,
        file_path: Optional[str] = None,
        created_at: Optional[datetime] = None,
        last_updated_at: Optional[datetime] = None,
    ) -> int:
        """
        Insert or update a plan.

        Parameters
        ----------
        plan_id : str
            Unique plan identifier
        name : str
            Plan name
        file_path : str, optional
            Path to the .plan.md file
        created_at : datetime, optional
            When plan was created
        last_updated_at : datetime, optional
            When plan was last updated

        Returns
        -------
        int
            Plan database ID
        """
        cursor = self.cursor()

        # Convert datetime to ISO string if provided
        created_str = created_at.isoformat() if created_at else None
        updated_str = last_updated_at.isoformat() if last_updated_at else None

        cursor.execute(
            """
            INSERT INTO plans (plan_id, name, file_path, created_at, last_updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(plan_id) DO UPDATE SET
                name = excluded.name,
                file_path = excluded.file_path,
                last_updated_at = excluded.last_updated_at
            """,
            (plan_id, name, file_path, created_str, updated_str),
        )
        self.commit()
        cursor.execute("SELECT id FROM plans WHERE plan_id = ?", (plan_id,))
        return cursor.fetchone()[0]

    def link_to_chat(self, chat_id: int, plan_id: int, relationship: str) -> None:
        """
        Link a chat to a plan.

        Parameters
        ----------
        chat_id : int
            Chat database ID
        plan_id : int
            Plan database ID
        relationship : str
            Relationship type: 'created', 'edited', or 'referenced'
        """
        cursor = self.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO chat_plans (chat_id, plan_id, relationship)
            VALUES (?, ?, ?)
            """,
            (chat_id, plan_id, relationship),
        )
        self.commit()

    def get_for_chat(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        Get all plans linked to a chat.

        Parameters
        ----------
        chat_id : int
            Chat database ID

        Returns
        -------
        List[Dict[str, Any]]
            List of plan dictionaries with relationship info
        """
        cursor = self.cursor()
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
            for row in cursor.fetchall()
        ]

    def get_chats(self, plan_id: int) -> List[Dict[str, Any]]:
        """
        Get all chats linked to a plan.

        Parameters
        ----------
        plan_id : int
            Plan database ID

        Returns
        -------
        List[Dict[str, Any]]
            List of chat dictionaries with relationship info
        """
        cursor = self.cursor()
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
            for row in cursor.fetchall()
        ]
