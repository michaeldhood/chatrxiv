"""
Database module for chat aggregation.

Provides SQLite database with FTS5 full-text search capabilities
using a repository pattern architecture.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .connection import DatabaseConnection
from .schema import SchemaManager
from .raw_storage import RawStorage
from .repositories.chat import ChatRepository
from .repositories.workspace import WorkspaceRepository
from .repositories.project import ProjectRepository
from .repositories.tag import TagRepository
from .repositories.plan import PlanRepository
from .repositories.activity import ActivityRepository
from .repositories.ingestion import IngestionStateRepository
from .search.fts import FTSManager
from .search.instant import instant_search
from .search.filtered import search_filtered, get_tag_facets, get_workspace_facets

# Import models for type hints
from src.core.models import Chat, Workspace, CursorActivity


class Database:
    """
    Main database facade combining all repositories.

    Provides a unified interface for database operations.

    Example
    -------
    >>> db = Database()
    >>> chat_id = db.chats.upsert(chat)
    >>> workspace = db.workspaces.get_by_hash("abc123")
    >>> results = instant_search(db.conn, "python")
    """

    def __init__(self, db_path: str = None):
        """
        Initialize database connection and repositories.

        Parameters
        ----------
        db_path : str, optional
            Path to database file. If None, uses default OS-specific location.
        """
        self.conn = DatabaseConnection(db_path)
        self._schema = SchemaManager(self.conn)
        self._schema.ensure()

        # Search (created first so it can be passed to ChatRepository)
        self.fts = FTSManager(self.conn)

        # Repositories
        self.chats = ChatRepository(self.conn, fts_manager=self.fts)
        self.workspaces = WorkspaceRepository(self.conn)
        self.projects = ProjectRepository(self.conn)
        self.tags = TagRepository(self.conn)
        self.plans = PlanRepository(self.conn)
        self.activity = ActivityRepository(self.conn)
        self.ingestion = IngestionStateRepository(self.conn)

    def close(self):
        """Close the database connection."""
        self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *args):
        """Context manager exit."""
        self.close()

    # =========================================================================
    # Backward compatibility delegate methods
    # These maintain API compatibility with the old ChatDatabase class
    # =========================================================================

    # --- Workspace methods ---
    def upsert_workspace(self, workspace: Workspace) -> int:
        """Delegate to WorkspaceRepository.upsert()."""
        return self.workspaces.upsert(workspace)

    def get_workspace_by_hash(self, workspace_hash: str) -> Optional[Dict[str, Any]]:
        """Delegate to WorkspaceRepository.get_by_hash()."""
        return self.workspaces.get_by_hash(workspace_hash)

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """Delegate to WorkspaceRepository.list()."""
        return self.workspaces.list()

    def assign_workspace_to_project(
        self, workspace_id: int, project_id: int
    ) -> None:
        """Delegate to WorkspaceRepository.assign_to_project()."""
        self.workspaces.assign_to_project(workspace_id, project_id)

    def assign_workspace_to_project_by_hash(
        self, workspace_hash: str, project_id: int
    ) -> bool:
        """Delegate to WorkspaceRepository.assign_to_project_by_hash()."""
        return self.workspaces.assign_to_project_by_hash(workspace_hash, project_id)

    # --- Chat methods ---
    def upsert_chat(self, chat: Chat) -> int:
        """Delegate to ChatRepository.upsert()."""
        return self.chats.upsert(chat)

    def get_chat(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Delegate to ChatRepository.get()."""
        return self.chats.get(chat_id)

    def get_chat_by_composer_id(
        self, composer_id: str
    ) -> Optional[Dict[str, Any]]:
        """Delegate to ChatRepository.get_by_composer_id()."""
        return self.chats.get_by_composer_id(composer_id)

    def list_chats(
        self,
        workspace_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
        empty_filter: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to ChatRepository.list()."""
        return self.chats.list(workspace_id, limit, offset, empty_filter, project_id)

    def count_chats(
        self,
        workspace_id: Optional[int] = None,
        empty_filter: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> int:
        """Delegate to ChatRepository.count()."""
        return self.chats.count(workspace_id, empty_filter, project_id)

    def delete_empty_chats(self) -> int:
        """Delegate to ChatRepository.delete_empty()."""
        return self.chats.delete_empty()

    def get_filter_options(self) -> Dict[str, Any]:
        """Delegate to ChatRepository.get_filter_options()."""
        return self.chats.get_filter_options()

    def get_last_updated_at(self) -> Optional[datetime]:
        """Delegate to ChatRepository.get_last_updated_at()."""
        return self.chats.get_last_updated_at()

    # --- Project methods ---
    def create_project(
        self, name: str, description: Optional[str] = None
    ) -> int:
        """Delegate to ProjectRepository.create()."""
        return self.projects.create(name, description)

    def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        """Delegate to ProjectRepository.get()."""
        return self.projects.get(project_id)

    def get_project_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Delegate to ProjectRepository.get_by_name()."""
        return self.projects.get_by_name(name)

    def list_projects(self) -> List[Dict[str, Any]]:
        """Delegate to ProjectRepository.list()."""
        return self.projects.list()

    def delete_project(self, project_id: int) -> bool:
        """Delegate to ProjectRepository.delete()."""
        return self.projects.delete(project_id)

    def get_workspaces_by_project(self, project_id: int) -> List[Dict[str, Any]]:
        """Delegate to ProjectRepository.get_workspaces()."""
        return self.projects.get_workspaces(project_id)

    # --- Tag methods ---
    def add_tags(self, chat_id: int, tags: List[str]) -> None:
        """Delegate to TagRepository.add()."""
        self.tags.add(chat_id, tags)

    def remove_tags(self, chat_id: int, tags: List[str]) -> None:
        """Delegate to TagRepository.remove()."""
        self.tags.remove(chat_id, tags)

    def get_chat_tags(self, chat_id: int) -> List[str]:
        """Delegate to TagRepository.get_for_chat()."""
        return self.tags.get_for_chat(chat_id)

    def get_all_tags(self) -> Dict[str, int]:
        """Delegate to TagRepository.get_all()."""
        return self.tags.get_all()

    def find_chats_by_tag(self, tag: str) -> List[int]:
        """Delegate to TagRepository.find_chats()."""
        return self.tags.find_chats(tag)

    def get_chat_files(self, chat_id: int) -> List[str]:
        """Delegate to TagRepository.get_chat_files()."""
        return self.tags.get_chat_files(chat_id)

    # --- Plan methods ---
    def upsert_plan(
        self,
        plan_id: str,
        name: str,
        file_path: Optional[str] = None,
        created_at: Optional[datetime] = None,
        last_updated_at: Optional[datetime] = None,
    ) -> int:
        """Delegate to PlanRepository.upsert()."""
        return self.plans.upsert(plan_id, name, file_path, created_at, last_updated_at)

    def link_chat_to_plan(
        self, chat_id: int, plan_id: int, relationship: str
    ) -> None:
        """Delegate to PlanRepository.link_to_chat()."""
        self.plans.link_to_chat(chat_id, plan_id, relationship)

    def get_plans_for_chat(self, chat_id: int) -> List[Dict[str, Any]]:
        """Delegate to PlanRepository.get_for_chat()."""
        return self.plans.get_for_chat(chat_id)

    def get_chats_for_plan(self, plan_id: int) -> List[Dict[str, Any]]:
        """Delegate to PlanRepository.get_chats()."""
        return self.plans.get_chats(plan_id)

    # --- Activity methods ---
    def upsert_activity(self, activity: CursorActivity) -> Optional[int]:
        """Delegate to ActivityRepository.upsert()."""
        return self.activity.upsert(activity)

    def get_activity_summary(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delegate to ActivityRepository.get_summary()."""
        return self.activity.get_summary(start_date, end_date)

    def get_activity_by_date_range(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Delegate to ActivityRepository.get_by_date_range()."""
        return self.activity.get_by_date_range(start_date, end_date, limit, offset)

    # --- Ingestion methods ---
    def get_ingestion_state(self, source: str = "cursor") -> Optional[Dict[str, Any]]:
        """Delegate to IngestionStateRepository.get_state()."""
        return self.ingestion.get_state(source)

    def update_ingestion_state(
        self,
        source: str,
        last_run_at: Optional[datetime] = None,
        last_processed_timestamp: Optional[str] = None,
        last_composer_id: Optional[str] = None,
        stats: Optional[Dict[str, int]] = None,
    ) -> None:
        """Delegate to IngestionStateRepository.update_state()."""
        self.ingestion.update_state(
            source, last_run_at, last_processed_timestamp, last_composer_id, stats
        )

    def get_chats_updated_since(
        self, timestamp: datetime, source: str = "cursor"
    ) -> List[str]:
        """Delegate to IngestionStateRepository.get_chats_updated_since()."""
        return self.ingestion.get_chats_updated_since(timestamp, source)

    # --- Search methods ---
    def search_chats(
        self, query: str, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Search chats using full-text search (legacy method).

        Uses the message_fts table for backward compatibility.
        For new code, use instant_search or search_with_snippets_filtered.
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT c.id, c.cursor_composer_id, c.title, c.mode, c.created_at,
                   c.source, c.messages_count, w.workspace_hash, w.resolved_path
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

            tags_by_chat: Dict[int, List[str]] = {}
            for row in cursor.fetchall():
                cid, tag = row
                if cid not in tags_by_chat:
                    tags_by_chat[cid] = []
                tags_by_chat[cid].append(tag)

            for result in results:
                result["tags"] = tags_by_chat.get(result["id"], [])

        return results

    def count_search(self, query: str) -> int:
        """
        Count search results for a query (legacy method).

        Uses the message_fts table for backward compatibility.
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

    def instant_search(
        self, query: str, limit: int = 20, sort_by: str = "relevance"
    ) -> List[Dict[str, Any]]:
        """Delegate to instant_search function."""
        return instant_search(self.conn, query, limit, sort_by)

    def search_with_snippets(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "relevance",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Delegate to search_filtered function (no filters)."""
        return search_filtered(self.conn, query, None, None, None, limit, offset, sort_by)

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
        """Delegate to search_filtered function."""
        return search_filtered(
            self.conn, query, tag_filters, workspace_filters, project_id, limit, offset, sort_by
        )

    def get_search_tag_facets(
        self,
        query: str,
        tag_filters: Optional[List[str]] = None,
        workspace_filters: Optional[List[int]] = None,
    ) -> Dict[str, int]:
        """Delegate to get_tag_facets function."""
        return get_tag_facets(self.conn, query, tag_filters, workspace_filters)

    def get_search_workspace_facets(
        self,
        query: str,
        tag_filters: Optional[List[str]] = None,
        workspace_filters: Optional[List[int]] = None,
    ) -> Dict[int, Dict[str, Any]]:
        """Delegate to get_workspace_facets function."""
        return get_workspace_facets(self.conn, query, tag_filters, workspace_filters)

    # --- FTS methods ---
    def _rebuild_unified_fts(self) -> int:
        """Delegate to FTSManager.rebuild_unified_index()."""
        return self.fts.rebuild_unified_index()

    def _update_unified_fts(self, chat_id: int) -> None:
        """Delegate to FTSManager.update_chat_index()."""
        self.fts.update_chat_index(chat_id)


# Backwards compatibility alias
ChatDatabase = Database

__all__ = [
    # Main facade
    "Database",
    "ChatDatabase",  # backwards compatibility
    # Connection/Schema
    "DatabaseConnection",
    "SchemaManager",
    # Raw storage (ELT)
    "RawStorage",
    # Repositories
    "ChatRepository",
    "WorkspaceRepository",
    "ProjectRepository",
    "TagRepository",
    "PlanRepository",
    "ActivityRepository",
    "IngestionStateRepository",
    # Search
    "FTSManager",
    "instant_search",
    "search_filtered",
    "get_tag_facets",
    "get_workspace_facets",
]
