"""
Server-Sent Events (SSE) stream route.
"""
import os
import json
import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.core.db import ChatDatabase
from src.core.config import get_default_db_path

router = APIRouter()


def get_db():
    """Get database instance."""
    db_path = os.getenv('CHATRXIV_DB_PATH') or str(get_default_db_path())
    return ChatDatabase(db_path)


@router.get("/stream")
async def stream():
    """
    Server-Sent Events endpoint for live updates.
    
    Polls the database every 2 seconds for changes and pushes updates to connected clients.
    """
    async def event_generator():
        """Async generator for SSE stream."""
        db = get_db()
        try:
            last_seen = db.get_last_updated_at()
            
            # Send initial connection message
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            
            while True:
                await asyncio.sleep(2)  # Check every 2 seconds
                
                # Check database for updates
                current = db.get_last_updated_at()
                if current and current != last_seen:
                    last_seen = current
                    # Send update event
                    yield f"data: {json.dumps({'type': 'update', 'timestamp': current})}\n\n"
        finally:
            db.close()
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
