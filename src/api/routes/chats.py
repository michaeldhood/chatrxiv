"""
Chats API routes.
"""
import os
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

from src.core.db import ChatDatabase
from src.core.config import get_default_db_path
from src.services.search import ChatSearchService
from src.api.schemas import ChatSummary, ChatsResponse, ChatDetail, FilterOptionsResponse, FilterOption

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
        total = search_service.count_chats(empty_filter=empty_filter)
        
        return ChatsResponse(
            chats=[ChatSummary(**chat) for chat in chats],
            total=total,
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
        
        # Process messages - group tool calls together
        # Frontend expects this for collapsible tool call groups
        processed_messages = []
        tool_call_group = []
        
        for msg in chat.get('messages', []):
            msg_type = msg.get('message_type', 'response')
            
            # Skip empty messages
            if msg_type == 'empty':
                continue
                
            # Group consecutive tool calls
            if msg_type == 'tool_call':
                tool_call_group.append(msg)
            else:
                # If we have accumulated tool calls, add them as a group
                if tool_call_group:
                    processed_messages.append({
                        'type': 'tool_call_group',
                        'tool_calls': tool_call_group.copy()
                    })
                    tool_call_group = []
                
                # Add the current message
                processed_messages.append({
                    'type': 'message',
                    'data': msg
                })
        
        # Don't forget remaining tool calls
        if tool_call_group:
            processed_messages.append({
                'type': 'tool_call_group',
                'tool_calls': tool_call_group
            })
        
        chat['processed_messages'] = processed_messages
        
        return ChatDetail(**chat)
    finally:
        db.close()


@router.get("/filter-options", response_model=FilterOptionsResponse)
def get_filter_options():
    """
    Get all available filter options (sources, modes) with counts.
    
    Used to populate filter dropdowns in the UI. Returns all distinct
    values regardless of current pagination.
    """
    db = get_db()
    try:
        options = db.get_filter_options()
        return FilterOptionsResponse(
            sources=[FilterOption(**s) for s in options["sources"]],
            modes=[FilterOption(**m) for m in options["modes"]]
        )
    finally:
        db.close()
