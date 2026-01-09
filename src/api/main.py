"""
FastAPI application entry point for chatrxiv API.

Provides REST API endpoints and integrates file watching for automatic
ingestion of new chats from Cursor.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import chats, search, stream

logger = logging.getLogger(__name__)

# Global watcher instance (managed by lifespan)
_watcher: Optional["IngestionWatcher"] = None


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan manager for startup/shutdown tasks.

    On startup:
    - Performs initial ingestion (if watching enabled)
    - Starts file watcher for automatic updates

    On shutdown:
    - Stops file watcher gracefully
    """
    global _watcher

    watch_enabled = os.getenv("CHATRXIV_WATCH", "true").lower() == "true"

    if watch_enabled:
        from src.services.watcher import IngestionWatcher

        logger.info("Performing initial ingestion...")
        _do_ingestion()

        logger.info("Starting file watcher for automatic updates...")
        _watcher = IngestionWatcher(
            ingestion_callback=_do_ingestion, debounce_seconds=5.0, poll_interval=30.0
        )
        _watcher.start()
        logger.info("File watcher started - new chats will be auto-ingested")
    else:
        logger.info("File watching disabled (CHATRXIV_WATCH=false)")

    yield  # App runs here

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
