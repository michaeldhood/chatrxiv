"""
Chats API routes.
"""
import os
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

from src.core.db import ChatDatabase
from src.core.config import get_default_db_path
from src.services.search import ChatSearchService
from src.api.schemas import ChatSummary, ChatsResponse, ChatDetail

router = APIRouter()


def get_db():
    """Get database instance."""
    db_path = os.getenv('CHATRXIV_DB_PATH') or str(get_default_db_path())
    return ChatDatabase(db_path)


@router.get("/chats", response_model=ChatsResponse)
def get_chats(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    filter: Optional[str] = Query(None, alias="filter")
):
    """
    Get paginated list of chats.
    
    Parameters
    ----
    page : int
        Page number (1-indexed)
    limit : int
        Results per page (max 100)
    filter : str, optional
        Filter by empty status: 'empty', 'non_empty', or None (all)
    """
    db = get_db()
    try:
        search_service = ChatSearchService(db)
        
        offset = (page - 1) * limit
        empty_filter = filter  # 'empty', 'non_empty', or None
        
        chats = search_service.list_chats(limit=limit, offset=offset, empty_filter=empty_filter)
        
        return ChatsResponse(
            chats=[ChatSummary(**chat) for chat in chats],
            page=page,
            limit=limit,
            filter=empty_filter
        )
    finally:
        db.close()


@router.get("/chats/{chat_id}", response_model=ChatDetail)
def get_chat(chat_id: int):
    """
    Get a specific chat by ID with all messages.
    
    Parameters
    ----
    chat_id : int
        Chat ID
    """
    db = get_db()
    try:
        search_service = ChatSearchService(db)
        chat = search_service.get_chat(chat_id)
        
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        return ChatDetail(**chat)
    finally:
        db.close()
