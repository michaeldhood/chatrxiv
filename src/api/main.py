"""
FastAPI application entry point for chatrxiv API.

Provides REST API endpoints and integrates file watching for automatic
ingestion of new chats from Cursor.
"""

import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import activity, chats, health, search, stream

logger = logging.getLogger(__name__)

# Global state (managed by lifespan)
_watcher: Optional["IngestionWatcher"] = None
_ingestion_complete = threading.Event()
_ingestion_thread: Optional[threading.Thread] = None


def _do_ingestion():
    """
    Perform incremental ingestion in background.

    Creates a fresh database connection for thread safety.
    """
    from src.core.config import get_default_db_path
    from src.core.db import ChatDatabase
    from src.services.aggregator import ChatAggregator

    db_path = os.getenv("CHATRXIV_DB_PATH") or str(get_default_db_path())
    db = ChatDatabase(db_path)

    try:
        aggregator = ChatAggregator(db)
        stats = aggregator.ingest_all(incremental=True)
        logger.info(
            "Auto-ingestion complete: %d ingested, %d skipped, %d errors",
            stats["ingested"],
            stats["skipped"],
            stats["errors"],
        )
    except Exception as e:
        logger.error("Error during automatic ingestion: %s", e)
    finally:
        db.close()


def _background_ingestion():
    """Run initial ingestion in background thread."""
    try:
        _do_ingestion()
    finally:
        _ingestion_complete.set()
        logger.info("Background ingestion complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan manager for startup/shutdown tasks.

    On startup:
    - Starts initial ingestion in background thread (non-blocking)
    - Starts file watcher for automatic updates

    On shutdown:
    - Stops file watcher gracefully
    """
    global _watcher, _ingestion_thread

    watch_enabled = os.getenv("CHATRXIV_WATCH", "true").lower() == "true"

    if watch_enabled:
        from src.services.watcher import IngestionWatcher

        # Start ingestion in background thread (non-blocking)
        logger.info("Starting background ingestion...")
        _ingestion_thread = threading.Thread(target=_background_ingestion, daemon=True)
        _ingestion_thread.start()

        # Start file watcher for subsequent updates
        logger.info("Starting file watcher for automatic updates...")
        _watcher = IngestionWatcher(
            ingestion_callback=_do_ingestion, debounce_seconds=5.0, poll_interval=30.0
        )
        _watcher.start()
        logger.info("Server ready (ingestion running in background)")
    else:
        _ingestion_complete.set()  # Mark as complete if watching disabled
        logger.info("File watching disabled (CHATRXIV_WATCH=false)")

    yield  # Server is ready immediately

    # Shutdown
    if _watcher:
        logger.info("Stopping file watcher...")
        _watcher.stop()
        logger.info("File watcher stopped")


app = FastAPI(title="chatrxiv API", version="1.0.0", lifespan=lifespan)

# CORS middleware for Next.js frontend
# Allow origins from environment variable or default to localhost
cors_origins = os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(chats.router, prefix="/api", tags=["chats"])
app.include_router(search.router, prefix="/api", tags=["search"])
app.include_router(stream.router, prefix="/api", tags=["stream"])
app.include_router(activity.router, prefix="/api", tags=["activity"])
app.include_router(health.router, prefix="/api", tags=["health"])
