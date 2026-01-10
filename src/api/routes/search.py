"""
Search API routes.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from src.api.deps import get_db
from src.api.schemas import (
    InstantSearchResponse,
    SearchFacetsResponse,
    SearchResponse,
    SearchResult,
    WorkspaceFacet,
)
from src.core.db import ChatDatabase
from src.services.search import ChatSearchService

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    sort: str = Query("relevance", regex="^(relevance|date)$"),
    db: ChatDatabase = Depends(get_db),
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
    db : ChatDatabase
        Database instance (injected via dependency)
    """
    search_service = ChatSearchService(db)

    offset = (page - 1) * limit
    results, total = search_service.search_with_total(
        q, limit=limit, offset=offset, sort_by=sort
    )

    return SearchResponse(
        query=q,
        results=[SearchResult(**result) for result in results],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/instant-search", response_model=InstantSearchResponse)
def instant_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    db: ChatDatabase = Depends(get_db),
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
    db : ChatDatabase
        Database instance (injected via dependency)
    """
    query = q.strip()

    if not query or len(query) < 2:
        return InstantSearchResponse(query=query, results=[], count=0)

    search_service = ChatSearchService(db)
    results = search_service.instant_search(query, limit=limit)

    return InstantSearchResponse(
        query=query,
        results=[SearchResult(**result) for result in results],
        count=len(results),
    )


@router.get("/search/facets", response_model=SearchFacetsResponse)
def search_with_facets(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    sort: str = Query("relevance", regex="^(relevance|date)$"),
    tags: Optional[List[str]] = Query(None),
    workspaces: Optional[List[int]] = Query(None),
    db: ChatDatabase = Depends(get_db),
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
    db : ChatDatabase
        Database instance (injected via dependency)
    """
    search_service = ChatSearchService(db)

    offset = (page - 1) * limit

    # Get results with facets
    results, total, tag_facets, workspace_facets_dict = (
        search_service.search_with_facets(
            q,
            tag_filters=tags if tags else None,
            workspace_filters=workspaces if workspaces else None,
            limit=limit,
            offset=offset,
            sort_by=sort,
        )
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
        sort_by=sort,
    )
