"""
Pydantic schemas for API request/response models.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """Individual message in a chat."""

    model_config = ConfigDict(from_attributes=True)

    role: str
    text: Optional[str] = None
    rich_text: Optional[str] = None
    created_at: Optional[str] = None
    bubble_id: Optional[str] = None
    message_type: str = Field(default="response")


class ChatSummary(BaseModel):
    """Chat summary for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    composer_id: Optional[str] = None
    title: Optional[str] = None
    mode: Optional[str] = None
    created_at: Optional[str] = None
    source: Optional[str] = None
    messages_count: int = 0
    workspace_hash: Optional[str] = None
    workspace_path: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class PlanInfo(BaseModel):
    """Plan information linked to a chat."""

    id: int
    plan_id: str
    name: str
    file_path: Optional[str] = None
    relationship: str  # 'created', 'edited', or 'referenced'


class ChatDetail(BaseModel):
    """Full chat with all messages."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    composer_id: Optional[str] = None
    title: Optional[str] = None
    mode: Optional[str] = None
    created_at: Optional[str] = None
    source: Optional[str] = None
    messages_count: int = 0
    workspace_hash: Optional[str] = None
    workspace_path: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    files: List[str] = Field(default_factory=list)
    plans: List[PlanInfo] = Field(default_factory=list)
    messages: List[Message] = Field(default_factory=list)
    processed_messages: List[Dict[str, Any]] = Field(default_factory=list)


class SearchResult(BaseModel):
    """Search result with highlighted snippet."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    composer_id: Optional[str] = None
    title: Optional[str] = None
    mode: Optional[str] = None
    created_at: Optional[str] = None
    source: Optional[str] = None
    messages_count: int = 0
    workspace_hash: Optional[str] = None
    workspace_path: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    snippet: Optional[str] = None


class ChatsResponse(BaseModel):
    """Response for /api/chats endpoint."""

    chats: List[ChatSummary]
    total: int
    page: int
    limit: int
    filter: Optional[str] = None


class SearchResponse(BaseModel):
    """Response for /api/search endpoint."""

    query: str
    results: List[SearchResult]
    total: int
    page: int
    limit: int


class InstantSearchResponse(BaseModel):
    """Response for /api/instant-search endpoint."""

    query: str
    results: List[SearchResult]
    count: int


class WorkspaceFacet(BaseModel):
    """Workspace facet information."""

    count: int
    resolved_path: Optional[str] = None
    workspace_hash: Optional[str] = None
    display_name: Optional[str] = None


class SearchFacetsResponse(BaseModel):
    """Response for search with facets."""

    query: str
    results: List[SearchResult]
    total: int
    page: int
    limit: int
    tag_facets: Dict[str, int] = Field(default_factory=dict)
    workspace_facets: Dict[int, WorkspaceFacet] = Field(default_factory=dict)
    active_filters: List[str] = Field(default_factory=list)
    active_workspace_filters: List[int] = Field(default_factory=list)
    sort_by: str = "relevance"


class FilterOption(BaseModel):
    """A filter option with its count."""

    value: str
    count: int


class FilterOptionsResponse(BaseModel):
    """Response for /api/filter-options endpoint."""

    sources: List[FilterOption] = Field(default_factory=list)
    modes: List[FilterOption] = Field(default_factory=list)
