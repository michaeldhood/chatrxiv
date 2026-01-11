"""
Project repository for database operations on projects.
"""

from typing import Any, Dict, List, Optional

from .base import BaseRepository


class ProjectRepository(BaseRepository):
    """
    Repository for project CRUD operations.

    Handles project creation, retrieval, listing, and workspace assignment.
    """

    def create(self, name: str, description: Optional[str] = None) -> int:
        """
        Create a new project.

        Parameters
        ----------
        name : str
            Unique project name
        description : str, optional
            Project description

        Returns
        -------
        int
            The new project's ID

        Raises
        ------
        sqlite3.IntegrityError
            If project name already exists
        """
        cursor = self.cursor()
        cursor.execute(
            """
            INSERT INTO projects (name, description)
            VALUES (?, ?)
        """,
            (name, description),
        )
        self.commit()
        return cursor.lastrowid

    def get(self, project_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a project by ID.

        Parameters
        ----------
        project_id : int
            Project ID

        Returns
        -------
        Optional[Dict[str, Any]]
            Project data or None if not found
        """
        cursor = self.cursor()
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

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a project by name.

        Parameters
        ----------
        name : str
            Project name

        Returns
        -------
        Optional[Dict[str, Any]]
            Project data or None if not found
        """
        cursor = self.cursor()
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

    def list(self) -> List[Dict[str, Any]]:
        """
        List all projects with workspace counts.

        Returns
        -------
        List[Dict[str, Any]]
            List of projects with workspace counts
        """
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT p.id, p.name, p.description, p.created_at,
                   COUNT(w.id) as workspace_count
            FROM projects p
            LEFT JOIN workspaces w ON w.project_id = p.id
            GROUP BY p.id
            ORDER BY p.name
        """
        )
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

    def delete(self, project_id: int) -> bool:
        """
        Delete a project. Workspaces are unlinked but not deleted.

        Parameters
        ----------
        project_id : int
            Project ID to delete

        Returns
        -------
        bool
            True if project was deleted, False if not found
        """
        cursor = self.cursor()
        # Unlink workspaces first
        cursor.execute(
            "UPDATE workspaces SET project_id = NULL WHERE project_id = ?",
            (project_id,),
        )
        # Delete project
        cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.commit()
        return cursor.rowcount > 0

    def get_workspaces(self, project_id: int) -> List[Dict[str, Any]]:
        """
        Get all workspaces in a project.

        Parameters
        ----------
        project_id : int
            Project ID

        Returns
        -------
        List[Dict[str, Any]]
            List of workspace records
        """
        cursor = self.cursor()
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
