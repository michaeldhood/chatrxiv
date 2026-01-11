"""
Database constants for the chat aggregation system.

These constants configure FTS5 search weights, pagination defaults,
and other database-related configuration values.
"""

# BM25 weights for unified_fts columns
# Higher weights = more important in search ranking
# Column order: title, content_type, message_text, tags, files
BM25_WEIGHTS = (10.0, 0.5, 1.0, 3.0, 1.0)

# Snippet configuration
SNIPPET_TOKENS_INSTANT = 32  # For typeahead/instant search
SNIPPET_TOKENS_FULL = 64  # For paginated search results

# Pagination defaults
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
