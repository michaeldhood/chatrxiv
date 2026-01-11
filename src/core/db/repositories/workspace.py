"""
Workspace repository for database operations on workspaces.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.models import Workspace
from .base import BaseRepository


class WorkspaceRepository(BaseRepository):
    """
    Repository for workspace CRUD operations.

    Handles workspace creation, retrieval, and project assignment.
    """

    def upsert(self, workspace: Workspace) -> int:
        """
        Insert or update a workspace.

        Parameters
        ----------
        workspace : Workspace
            Workspace to upsert

        Returns
        -------
        int
            Workspace ID
        """
        cursor = self.cursor()

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

        self.commit()
        return workspace_id

    def get_by_hash(self, workspace_hash: str) -> Optional[Dict[str, Any]]:
        """
        Get a workspace by its hash.

        Parameters
        ----------
        workspace_hash : str
            Workspace hash to look up

        Returns
        -------
        Optional[Dict[str, Any]]
            Workspace data or None if not found
        """
        cursor = self.cursor()
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

    def list(self) -> List[Dict[str, Any]]:
        """
        List all workspaces with project info.

        Returns
        -------
        List[Dict[str, Any]]
            List of workspaces with project information
        """
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT w.id, w.workspace_hash, w.folder_uri, w.resolved_path,
                   w.first_seen_at, w.last_seen_at, w.project_id,
                   p.name as project_name,
                   (SELECT COUNT(*) FROM chats c WHERE c.workspace_id = w.id) as chat_count
            FROM workspaces w
            LEFT JOIN projects p ON w.project_id = p.id
            ORDER BY w.last_seen_at DESC
            """
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
                "project_name": row[7],
                "chat_count": row[8],
            }
            for row in cursor.fetchall()
        ]

    def assign_to_project(self, workspace_id: int, project_id: Optional[int]) -> None:
        """
        Assign a workspace to a project.

        Parameters
        ----------
        workspace_id : int
            Workspace database ID
        project_id : int, optional
            Project database ID (None to unassign)
        """
        cursor = self.cursor()
        cursor.execute(
            "UPDATE workspaces SET project_id = ? WHERE id = ?",
            (project_id, workspace_id),
        )
        self.commit()

    def assign_to_project_by_hash(
        self, workspace_hash: str, project_id: int
    ) -> Optional[int]:
        """
        Assign a workspace to a project by workspace hash.

        Parameters
        ----------
        workspace_hash : str
            Workspace hash
        project_id : int
            Project database ID

        Returns
        -------
        Optional[int]
            Workspace ID if found and updated, None otherwise
        """
        cursor = self.cursor()
        cursor.execute(
            "SELECT id FROM workspaces WHERE workspace_hash = ?",
            (workspace_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        workspace_id = row[0]
        cursor.execute(
            "UPDATE workspaces SET project_id = ? WHERE id = ?",
            (project_id, workspace_id),
        )
        self.commit()
        return workspace_id
