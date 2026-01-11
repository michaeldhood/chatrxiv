"""
Instant search for typeahead/live search functionality.
"""

import logging
import sqlite3
from typing import Any, Dict, List, TYPE_CHECKING

from ..constants import BM25_WEIGHTS, SNIPPET_TOKENS_INSTANT

if TYPE_CHECKING:
    from ..connection import DatabaseConnection

logger = logging.getLogger(__name__)


def instant_search(
    conn: "DatabaseConnection",
    query: str,
    limit: int = 20,
    sort_by: str = "relevance",
) -> List[Dict[str, Any]]:
    """
    Fast instant search for typeahead/live search.

    Searches across chat titles, messages, tags, and files.
    Returns results with highlighted snippets.

    Parameters
    ----------
    conn : DatabaseConnection
        Database connection
    query : str
        Search query (automatically handles prefix matching)
    limit : int
        Maximum results to return
    sort_by : str
        Sort order: 'relevance' (BM25) or 'date' (newest first)

    Returns
    -------
    List[Dict[str, Any]]
        Search results with snippets and highlights
    """
    cursor = conn.cursor()

    # Clean the query and add prefix matching for each term
    # This enables search-as-you-type behavior
    terms = query.strip().split()
    if not terms:
        return []

    # Build FTS5 query with prefix matching on last term
    # e.g., "hello wor" -> 'hello wor*'
    fts_query = " ".join(terms[:-1] + [terms[-1] + "*"]) if terms else ""

    # Clean query for title matching (used for boosting exact matches)
    clean_query = query.strip().lower()

    # Determine sort order
    # For relevance sorting, we use a compound ORDER BY:
    # 1. Exact title match (highest priority)
    # 2. Title starts with query
    # 3. Title contains query
    # 4. BM25 weighted score
    if sort_by == "date":
        order_clause = "ORDER BY c.created_at DESC"
    else:
        # title_boost: 0 = exact match, 1 = starts with, 2 = contains, 3 = no title match
        order_clause = "ORDER BY title_boost, rank"

    # Build BM25 function call with column weights
    bm25_call = f"bm25(unified_fts, {', '.join(str(w) for w in BM25_WEIGHTS)})"

    try:
        # Search with snippet generation
        # snippet() function: table, column_idx, start_mark, end_mark, ellipsis, max_tokens
        cursor.execute(
            f"""
            SELECT
                fts.chat_id,
                c.cursor_composer_id,
                c.title,
                c.mode,
                c.created_at,
                c.source,
                c.messages_count,
                w.workspace_hash,
                w.resolved_path,
                snippet(unified_fts, 3, '<mark>', '</mark>', '...', {SNIPPET_TOKENS_INSTANT}) as snippet,
                {bm25_call} as rank,
                CASE
                    WHEN LOWER(c.title) = ? THEN 0
                    WHEN LOWER(c.title) LIKE ? || '%' THEN 1
                    WHEN LOWER(c.title) LIKE '%' || ? || '%' THEN 2
                    ELSE 3
                END as title_boost
            FROM unified_fts fts
            INNER JOIN chats c ON fts.chat_id = c.id
            LEFT JOIN workspaces w ON c.workspace_id = w.id
            WHERE unified_fts MATCH ?
            {order_clause}
            LIMIT ?
        """,
            (clean_query, clean_query, clean_query, fts_query, limit),
        )

        results = []
        chat_ids = []
        for row in cursor.fetchall():
            chat_id = row[0]
            chat_ids.append(chat_id)
            results.append(
                {
                    "id": chat_id,
                    "composer_id": row[1],
                    "title": row[2] or "Untitled Chat",
                    "mode": row[3],
                    "created_at": row[4],
                    "source": row[5],
                    "messages_count": row[6] or 0,
                    "workspace_hash": row[7],
                    "workspace_path": row[8],
                    "snippet": row[9],  # Highlighted snippet
                    "rank": row[10],
                    "tags": [],
                }
            )

        # Batch load tags
        if chat_ids:
            placeholders = ",".join(["?"] * len(chat_ids))
            cursor.execute(
                f"""
                SELECT chat_id, tag FROM tags
                WHERE chat_id IN ({placeholders})
                ORDER BY chat_id, tag
            """,
                chat_ids,
            )

            tags_by_chat: Dict[int, List[str]] = {}
            for row in cursor.fetchall():
                chat_id, tag = row
                if chat_id not in tags_by_chat:
                    tags_by_chat[chat_id] = []
                tags_by_chat[chat_id].append(tag)

            for result in results:
                result["tags"] = tags_by_chat.get(result["id"], [])

        return results

    except sqlite3.OperationalError as e:
        # Handle malformed FTS queries gracefully
        logger.debug("FTS query error for '%s': %s", query, e)
        return []
