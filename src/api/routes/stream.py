"""
Server-Sent Events (SSE) stream route.

Provides real-time updates to the frontend when new chats are ingested.
The endpoint polls the database every 2 seconds for changes.
"""
import os
import json
import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.core.db import ChatDatabase
from src.core.config import get_default_db_path

router = APIRouter()


def get_db_path() -> str:
    """Get database path from env or default."""
    return os.getenv('CHATRXIV_DB_PATH') or str(get_default_db_path())


def check_for_updates(db_path: str) -> str | None:
    """
    Check database for latest update timestamp.
    
    Opens a fresh connection each time to ensure we see changes
    committed by other processes (daemon, CLI ingest).
    """
    db = ChatDatabase(db_path)
    try:
        return db.get_last_updated_at()
    finally:
        db.close()


@router.get("/stream")
async def stream():
    """
    Server-Sent Events endpoint for live updates.
    
    Polls the database every 2 seconds for changes and pushes updates to connected clients.
    
    Notes
    -----
    - Opens a fresh DB connection on each poll to ensure visibility of changes
      from other processes (daemon writes, CLI ingest)
    - Requires the daemon or manual ingest to actually populate new chats
    """
    async def event_generator():
        """Async generator for SSE stream."""
        try:
            db_path = get_db_path()
            
            # Get initial timestamp
            last_seen = check_for_updates(db_path)
            
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            
            while True:
                await asyncio.sleep(2)  # Check every 2 seconds
                
                # Fresh connection each time to see changes from other processes
                current = check_for_updates(db_path)
                if current and current != last_seen:
                    last_seen = current
                    # Send update event
                    yield f"data: {json.dumps({'type': 'update', 'timestamp': current})}\n\n"
        except asyncio.CancelledError:
            # Client disconnected - this is normal, exit silently
            return
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
