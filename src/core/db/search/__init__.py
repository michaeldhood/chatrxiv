"""
Search module for full-text search functionality.

Provides instant search and filtered search with facets.
"""

from .fts import FTSManager
from .instant import instant_search
from .filtered import search_filtered, get_tag_facets, get_workspace_facets

__all__ = [
    "FTSManager",
    "instant_search",
    "search_filtered",
    "get_tag_facets",
    "get_workspace_facets",
]
