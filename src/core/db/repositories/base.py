"""
Base repository class providing common database operations.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..connection import DatabaseConnection


class BaseRepository:
    """
    Base class for all repository implementations.

    Provides common database access patterns and utilities.
    """

    def __init__(self, conn: "DatabaseConnection"):
        """
        Initialize repository with database connection.

        Parameters
        ----------
        conn : DatabaseConnection
            Database connection to use for operations.
        """
        self._conn = conn

    def cursor(self):
        """Get a new cursor for database operations."""
        return self._conn.cursor()

    def commit(self) -> None:
        """Commit the current transaction."""
        self._conn.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self._conn.rollback()
