"""
Filtered search with pagination, facets, and tag/workspace filtering.
"""

import logging
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from ..constants import BM25_WEIGHTS, SNIPPET_TOKENS_FULL

if TYPE_CHECKING:
    from ..connection import DatabaseConnection

logger = logging.getLogger(__name__)


def _build_fts_query(query: str) -> str:
    """Build FTS5 query with prefix matching on last term."""
    terms = query.strip().split()
    if not terms:
        return ""
    return " ".join(terms[:-1] + [terms[-1] + "*"])


def _batch_load_tags(cursor, chat_ids: List[int]) -> Dict[int, List[str]]:
    """Batch load tags for multiple chats."""
    if not chat_ids:
        return {}

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

    return tags_by_chat


def search_filtered(
    conn: "DatabaseConnection",
    query: str,
    tag_filters: Optional[List[str]] = None,
    workspace_filters: Optional[List[int]] = None,
    project_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "relevance",
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Full search with snippets, pagination, and filters.

    Parameters
    ----------
    conn : DatabaseConnection
        Database connection
    query : str
        Search query
    tag_filters : List[str], optional
        Only return chats that have ALL of these tags
    workspace_filters : List[int], optional
        Only return chats from these workspace IDs
    project_id : int, optional
        Only return chats from workspaces in this project
    limit : int
        Maximum results per page
    offset : int
        Pagination offset
    sort_by : str
        Sort order: 'relevance' (BM25) or 'date' (newest first)

    Returns
    -------
    Tuple[List[Dict], int]
        (results with snippets, total count)
    """
    cursor = conn.cursor()

    terms = query.strip().split()
    if not terms:
        return [], 0

    fts_query = _build_fts_query(query)
    clean_query = query.strip().lower()

    try:
        # Build filter conditions
        conditions = ["unified_fts MATCH ?"]
        params: List[Any] = [fts_query]

        # Build tag filter using subquery approach
        if tag_filters:
            tag_placeholders = ",".join(["?"] * len(tag_filters))
            tag_subquery = f"""
                SELECT chat_id
                FROM tags
                WHERE tag IN ({tag_placeholders})
                GROUP BY chat_id
                HAVING COUNT(DISTINCT tag) = ?
            """
            conditions.append(f"fts.chat_id IN ({tag_subquery})")
            params.extend(tag_filters)
            params.append(len(tag_filters))

        # Build workspace filter
        if workspace_filters:
            workspace_placeholders = ",".join(["?"] * len(workspace_filters))
            conditions.append(f"c.workspace_id IN ({workspace_placeholders})")
            params.extend(workspace_filters)

        # Build project filter
        if project_id:
            conditions.append("w.project_id = ?")
            params.append(project_id)

        where_clause = " AND ".join(conditions)

        # Get total count first
        cursor.execute(
            f"""
            SELECT COUNT(DISTINCT fts.chat_id)
            FROM unified_fts fts
            INNER JOIN chats c ON fts.chat_id = c.id
            LEFT JOIN workspaces w ON c.workspace_id = w.id
            WHERE {where_clause}
        """,
            params,
        )

        total = cursor.fetchone()[0]

        # Determine sort order
        if sort_by == "date":
            order_clause = "ORDER BY c.created_at DESC"
        else:
            order_clause = "ORDER BY title_boost, rank"

        # Build BM25 function call with column weights
        bm25_call = f"bm25(unified_fts, {', '.join(str(w) for w in BM25_WEIGHTS)})"

        # Get results with snippets
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
                snippet(unified_fts, 3, '<mark>', '</mark>', '...', {SNIPPET_TOKENS_FULL}) as snippet,
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
            WHERE {where_clause}
            {order_clause}
            LIMIT ? OFFSET ?
        """,
            [clean_query, clean_query, clean_query] + params + [limit, offset],
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
                    "snippet": row[9],
                    "rank": row[10],
                    "tags": [],
                }
            )

        # Batch load tags
        tags_by_chat = _batch_load_tags(cursor, chat_ids)
        for result in results:
            result["tags"] = tags_by_chat.get(result["id"], [])

        return results, total

    except sqlite3.OperationalError as e:
        logger.debug("FTS filtered query error for '%s': %s", query, e)
        return [], 0


def get_tag_facets(
    conn: "DatabaseConnection",
    query: str,
    tag_filters: Optional[List[str]] = None,
    workspace_filters: Optional[List[int]] = None,
) -> Dict[str, int]:
    """
    Get tag facet counts for search results.

    Returns counts of all tags across ALL matching chats (not just current page),
    useful for building filter UI sidebars.

    Parameters
    ----------
    conn : DatabaseConnection
        Database connection
    query : str
        Search query
    tag_filters : List[str], optional
        If provided, only count tags for chats that have ALL these tags
    workspace_filters : List[int], optional
        If provided, only count tags for chats in these workspaces

    Returns
    -------
    Dict[str, int]
        Mapping of tag -> count of chats with that tag
    """
    cursor = conn.cursor()

    terms = query.strip().split()
    if not terms:
        return {}

    fts_query = _build_fts_query(query)

    try:
        # Build conditions for matching chat IDs
        conditions = ["unified_fts MATCH ?"]
        params: List[Any] = [fts_query]

        if tag_filters:
            # Get chat IDs matching both FTS query AND all tag filters
            placeholders = ",".join(["?"] * len(tag_filters))
            tag_subquery = f"""
                SELECT chat_id
                FROM tags
                WHERE tag IN ({placeholders})
                GROUP BY chat_id
                HAVING COUNT(DISTINCT tag) = ?
            """
            conditions.append(f"fts.chat_id IN ({tag_subquery})")
            params.extend(tag_filters)
            params.append(len(tag_filters))

        if workspace_filters:
            workspace_placeholders = ",".join(["?"] * len(workspace_filters))
            conditions.append(f"c.workspace_id IN ({workspace_placeholders})")
            params.extend(workspace_filters)

        where_clause = " AND ".join(conditions)

        if tag_filters or workspace_filters:
            cursor.execute(
                f"""
                SELECT DISTINCT fts.chat_id
                FROM unified_fts fts
                INNER JOIN chats c ON fts.chat_id = c.id
                WHERE {where_clause}
            """,
                params,
            )
        else:
            cursor.execute(
                """
                SELECT DISTINCT chat_id
                FROM unified_fts
                WHERE unified_fts MATCH ?
            """,
                (fts_query,),
            )

        matching_chat_ids = [row[0] for row in cursor.fetchall()]

        if not matching_chat_ids:
            return {}

        # Get tag counts for matching chats
        placeholders = ",".join(["?"] * len(matching_chat_ids))
        cursor.execute(
            f"""
            SELECT tag, COUNT(*) as cnt
            FROM tags
            WHERE chat_id IN ({placeholders})
            GROUP BY tag
            ORDER BY cnt DESC, tag ASC
        """,
            matching_chat_ids,
        )

        return {row[0]: row[1] for row in cursor.fetchall()}

    except sqlite3.OperationalError as e:
        logger.debug("FTS facet query error for '%s': %s", query, e)
        return {}


def get_workspace_facets(
    conn: "DatabaseConnection",
    query: str,
    tag_filters: Optional[List[str]] = None,
    workspace_filters: Optional[List[int]] = None,
) -> Dict[int, Dict[str, Any]]:
    """
    Get workspace facet counts for search results.

    Returns counts of all workspaces across matching chats, useful for building filter UI.

    Parameters
    ----------
    conn : DatabaseConnection
        Database connection
    query : str
        Search query
    tag_filters : List[str], optional
        If provided, only count workspaces for chats that have ALL these tags
    workspace_filters : List[int], optional
        If provided, only count workspaces matching these workspace IDs

    Returns
    -------
    Dict[int, Dict[str, Any]]
        Mapping of workspace_id -> {'count': int, 'resolved_path': str, 'workspace_hash': str}
    """
    cursor = conn.cursor()

    terms = query.strip().split()
    if not terms:
        return {}

    fts_query = _build_fts_query(query)

    try:
        # Build base query to get matching chat IDs
        conditions = ["unified_fts MATCH ?"]
        params: List[Any] = [fts_query]

        # Add tag filters if provided
        if tag_filters:
            tag_placeholders = ",".join(["?"] * len(tag_filters))
            tag_subquery = f"""
                SELECT chat_id
                FROM tags
                WHERE tag IN ({tag_placeholders})
                GROUP BY chat_id
                HAVING COUNT(DISTINCT tag) = ?
            """
            conditions.append(f"fts.chat_id IN ({tag_subquery})")
            params.extend(tag_filters)
            params.append(len(tag_filters))

        # Add workspace filters if provided
        if workspace_filters:
            workspace_placeholders = ",".join(["?"] * len(workspace_filters))
            conditions.append(f"c.workspace_id IN ({workspace_placeholders})")
            params.extend(workspace_filters)

        where_clause = " AND ".join(conditions)

        # Get matching chat IDs
        cursor.execute(
            f"""
            SELECT DISTINCT fts.chat_id, c.workspace_id
            FROM unified_fts fts
            INNER JOIN chats c ON fts.chat_id = c.id
            WHERE {where_clause}
        """,
            params,
        )

        matching_chats = cursor.fetchall()

        if not matching_chats:
            return {}

        # Get workspace IDs and their chat counts
        workspace_counts: Dict[int, int] = {}
        for row in matching_chats:
            workspace_id = row[1]
            if workspace_id:
                if workspace_id not in workspace_counts:
                    workspace_counts[workspace_id] = 0
                workspace_counts[workspace_id] += 1

        if not workspace_counts:
            return {}

        # Get workspace details
        workspace_ids = list(workspace_counts.keys())
        placeholders = ",".join(["?"] * len(workspace_ids))
        cursor.execute(
            f"""
            SELECT id, workspace_hash, resolved_path
            FROM workspaces
            WHERE id IN ({placeholders})
        """,
            workspace_ids,
        )

        workspace_details = {
            row[0]: {"workspace_hash": row[1], "resolved_path": row[2]}
            for row in cursor.fetchall()
        }

        # Combine counts with details
        result: Dict[int, Dict[str, Any]] = {}
        for workspace_id, count in workspace_counts.items():
            details = workspace_details.get(workspace_id, {})
            result[workspace_id] = {
                "count": count,
                "resolved_path": details.get("resolved_path", ""),
                "workspace_hash": details.get("workspace_hash", ""),
            }

        return result

    except sqlite3.OperationalError as e:
        logger.debug("FTS workspace facet query error for '%s': %s", query, e)
        return {}
