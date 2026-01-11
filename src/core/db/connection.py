"""
Database connection management for the chat aggregation system.

Provides a DatabaseConnection class that handles SQLite connection
lifecycle, WAL mode configuration, and context manager support.
"""

import logging
import sqlite3
from typing import Optional

from src.core.config import get_default_db_path

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """
    SQLite database connection with WAL mode and context manager support.

    This class manages the database connection lifecycle and provides
    a clean interface for obtaining cursors and managing transactions.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database connection.

        Parameters
        ----------
        db_path : str, optional
            Path to database file. If None, uses default OS-specific location.
        """
        if db_path is None:
            db_path = str(get_default_db_path())

        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()

    def _connect(self) -> None:
        """Establish database connection with WAL mode."""
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # Enable WAL mode for concurrent read/write access
        # This allows the daemon (writer) and web server (reader) to access DB simultaneously
        cursor = self._conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.fetchone()  # Consume the result

        logger.debug("Database connection established: %s", self.db_path)

    @property
    def connection(self) -> sqlite3.Connection:
        """Get the underlying SQLite connection."""
        if self._conn is None:
            self._connect()
        return self._conn

    def cursor(self) -> sqlite3.Cursor:
        """Get a new cursor for the database connection."""
        return self.connection.cursor()

    def commit(self) -> None:
        """Commit the current transaction."""
        self.connection.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.connection.rollback()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("Database connection closed: %s", self.db_path)

    def __enter__(self) -> "DatabaseConnection":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - close connection."""
        self.close()
