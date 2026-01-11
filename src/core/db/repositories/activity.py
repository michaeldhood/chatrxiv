"""
Activity repository for database operations on cursor activity.
"""

from typing import Any, Dict, List, Optional

from src.core.models import CursorActivity
from .base import BaseRepository


class ActivityRepository(BaseRepository):
    """
    Repository for cursor activity tracking.

    Handles activity logging and summary statistics.
    """

    def upsert(self, activity: CursorActivity) -> Optional[int]:
        """
        Insert or update a cursor activity record.

        Uses INSERT OR IGNORE to prevent duplicates based on unique constraint.

        Parameters
        ----------
        activity : CursorActivity
            Activity to upsert

        Returns
        -------
        Optional[int]
            Activity ID (or existing ID if duplicate)
        """
        cursor = self.cursor()

        cursor.execute(
            """
            INSERT OR IGNORE INTO cursor_activity
            (date, kind, model, max_mode, input_tokens_with_cache, input_tokens_no_cache,
             cache_read_tokens, output_tokens, total_tokens, cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                activity.date.isoformat() if activity.date else None,
                activity.kind,
                activity.model,
                1 if activity.max_mode else 0 if activity.max_mode is False else None,
                activity.input_tokens_with_cache,
                activity.input_tokens_no_cache,
                activity.cache_read_tokens,
                activity.output_tokens,
                activity.total_tokens,
                activity.cost,
            ),
        )

        # If insert was ignored (duplicate), get the existing ID
        if cursor.lastrowid == 0:
            cursor.execute(
                """
                SELECT id FROM cursor_activity
                WHERE date = ? AND model = ? AND kind = ?
            """,
                (
                    activity.date.isoformat() if activity.date else None,
                    activity.model,
                    activity.kind,
                ),
            )
            row = cursor.fetchone()
            activity_id = row[0] if row else None
        else:
            activity_id = cursor.lastrowid

        self.commit()
        return activity_id

    def get_summary(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get summary statistics for cursor activity.

        Parameters
        ----------
        start_date : str, optional
            Start date (ISO format)
        end_date : str, optional
            End date (ISO format)

        Returns
        -------
        Dict[str, Any]
            Summary statistics
        """
        cursor = self.cursor()

        conditions = []
        params = []

        if start_date:
            conditions.append("date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("date <= ?")
            params.append(end_date)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Total cost
        cursor.execute(
            f"SELECT COALESCE(SUM(cost), 0) FROM cursor_activity {where_clause}",
            params,
        )
        total_cost = cursor.fetchone()[0] or 0.0

        # Total tokens
        cursor.execute(
            f"""
            SELECT
                COALESCE(SUM(input_tokens_with_cache), 0),
                COALESCE(SUM(input_tokens_no_cache), 0),
                COALESCE(SUM(cache_read_tokens), 0),
                COALESCE(SUM(output_tokens), 0),
                COALESCE(SUM(total_tokens), 0)
            FROM cursor_activity {where_clause}
        """,
            params,
        )
        row = cursor.fetchone()
        total_input_with_cache = row[0] or 0
        total_input_no_cache = row[1] or 0
        total_cache_read = row[2] or 0
        total_output_tokens = row[3] or 0
        total_tokens = row[4] or 0

        # Activity count by kind
        cursor.execute(
            f"""
            SELECT kind, COUNT(*)
            FROM cursor_activity {where_clause}
            GROUP BY kind
        """,
            params,
        )
        activity_by_kind = {row[0]: row[1] for row in cursor.fetchall()}

        # Cost by model - fix the SQL bug by properly handling empty where clause
        if where_clause:
            model_where = where_clause + " AND model IS NOT NULL"
        else:
            model_where = "WHERE model IS NOT NULL"

        cursor.execute(
            f"""
            SELECT model, COALESCE(SUM(cost), 0), COUNT(*)
            FROM cursor_activity {model_where}
            GROUP BY model
        """,
            params,
        )
        cost_by_model = {
            row[0]: {"cost": row[1] or 0.0, "count": row[2]}
            for row in cursor.fetchall()
        }

        return {
            "total_cost": total_cost,
            "total_input_tokens_with_cache": total_input_with_cache,
            "total_input_tokens_no_cache": total_input_no_cache,
            "total_cache_read_tokens": total_cache_read,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "activity_by_kind": activity_by_kind,
            "cost_by_model": cost_by_model,
        }

    def get_by_date_range(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Get activity records within a date range.

        Parameters
        ----------
        start_date : str, optional
            Start date (ISO format)
        end_date : str, optional
            End date (ISO format)
        limit : int, optional
            Maximum number of records to return
        offset : int
            Number of records to skip

        Returns
        -------
        List[Dict[str, Any]]
            List of activity records
        """
        cursor = self.cursor()

        conditions = []
        params = []

        if start_date:
            conditions.append("date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("date <= ?")
            params.append(end_date)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        limit_clause = ""
        if limit:
            limit_clause = f"LIMIT {limit} OFFSET {offset}"

        cursor.execute(
            f"""
            SELECT id, date, kind, model, max_mode, input_tokens_with_cache,
                   input_tokens_no_cache, cache_read_tokens, output_tokens,
                   total_tokens, cost
            FROM cursor_activity
            {where_clause}
            ORDER BY date DESC
            {limit_clause}
        """,
            params,
        )

        return [
            {
                "id": row[0],
                "date": row[1],
                "kind": row[2],
                "model": row[3],
                "max_mode": bool(row[4]) if row[4] is not None else None,
                "input_tokens_with_cache": row[5],
                "input_tokens_no_cache": row[6],
                "cache_read_tokens": row[7],
                "output_tokens": row[8],
                "total_tokens": row[9],
                "cost": row[10],
            }
            for row in cursor.fetchall()
        ]
