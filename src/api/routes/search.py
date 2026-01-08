"""
Search API routes.
"""
import os
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException

from src.core.db import ChatDatabase
from src.core.config import get_default_db_path
from src.services.search import ChatSearchService
from src.api.schemas import (
    SearchResult, 
    SearchResponse, 
    InstantSearchResponse,
    SearchFacetsResponse,
    WorkspaceFacet
)

router = APIRouter()


def get_db():
    """Get database instance."""
    db_path = os.getenv('CHATRXIV_DB_PATH') or str(get_default_db_path())
    return ChatDatabase(db_path)


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    sort: str = Query("relevance", regex="^(relevance|date)$")
):
    """
    Search chats by text content.
    
    Parameters
    ----
    q : str
        Search query (required)
    page : int
        Page number (1-indexed)
    limit : int
        Results per page (max 100)
    sort : str
        Sort order: 'relevance' or 'date'
    """
    if not q:
        raise HTTPException(status_code=400, detail="Query required")
    
    db = get_db()
    try:
        search_service = ChatSearchService(db)
        
        offset = (page - 1) * limit
        results, total = search_service.search_with_total(q, limit=limit, offset=offset, sort_by=sort)
        
        return SearchResponse(
            query=q,
            results=[SearchResult(**result) for result in results],
            total=total,
            page=page,
            limit=limit
        )
    finally:
        db.close()


@router.get("/instant-search", response_model=InstantSearchResponse)
def instant_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Fast instant search for typeahead/live search.
    
    Optimized for speed - returns within milliseconds.
    Results include highlighted snippets showing match context.
    
    Parameters
    ----
    q : str
        Search query (required, min 1 char)
    limit : int
        Maximum results (default 10, max 50)
    """
    query = q.strip()
    
    if not query or len(query) < 2:
        return InstantSearchResponse(
            query=query,
            results=[],
            count=0
        )
    
    db = get_db()
    try:
        search_service = ChatSearchService(db)
        results = search_service.instant_search(query, limit=limit)
        
        return InstantSearchResponse(
            query=query,
            results=[SearchResult(**result) for result in results],
            count=len(results)
        )
    finally:
        db.close()


@router.get("/search/facets", response_model=SearchFacetsResponse)
def search_with_facets(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    sort: str = Query("relevance", regex="^(relevance|date)$"),
    tags: Optional[List[str]] = Query(None),
    workspaces: Optional[List[int]] = Query(None)
):
    """
    Search with tag and workspace facets for building filter UI.
    
    Returns search results along with tag and workspace facet counts.
    
    Parameters
    ----
    q : str
        Search query (required)
    page : int
        Page number (1-indexed)
    limit : int
        Results per page (max 100)
    sort : str
        Sort order: 'relevance' or 'date'
    tags : List[str], optional
        Filter by tags (comma-separated or multiple params)
    workspaces : List[int], optional
        Filter by workspace IDs (comma-separated or multiple params)
    """
    db = get_db()
    try:
        search_service = ChatSearchService(db)
        
        offset = (page - 1) * limit
        
        # Get results with facets
        results, total, tag_facets, workspace_facets_dict = search_service.search_with_facets(
            q,
            tag_filters=tags if tags else None,
            workspace_filters=workspaces if workspaces else None,
            limit=limit,
            offset=offset,
            sort_by=sort
        )
        
        # Convert workspace facets dict to WorkspaceFacet models
        workspace_facets = {}
        for ws_id, ws_info in workspace_facets_dict.items():
            workspace_facets[ws_id] = WorkspaceFacet(**ws_info)
        
        return SearchFacetsResponse(
            query=q,
            results=[SearchResult(**result) for result in results],
            total=total,
            page=page,
            limit=limit,
            tag_facets=tag_facets,
            workspace_facets=workspace_facets,
            active_filters=tags if tags else [],
            active_workspace_filters=workspaces if workspaces else [],
            sort_by=sort
        )
    finally:
        db.close()
