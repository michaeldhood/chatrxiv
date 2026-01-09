"""
FastAPI dependencies for shared resources.

Provides dependency injection for database connections and other shared resources.
"""

import os
from typing import Generator

from src.core.config import get_default_db_path
from src.core.db import ChatDatabase


def get_db() -> Generator[ChatDatabase, None, None]:
    """
    Dependency that provides database connection and ensures cleanup.

    Yields
    ----
    ChatDatabase
        Database instance

    Notes
    -----
    Uses FastAPI's dependency injection system to ensure connections
    are properly closed after each request. This prevents connection
    leaks and improves performance by reusing connections within a request.
    """
    db_path = os.getenv("CHATRXIV_DB_PATH") or str(get_default_db_path())
    db = ChatDatabase(db_path)
    try:
        yield db
    finally:
        db.close()
