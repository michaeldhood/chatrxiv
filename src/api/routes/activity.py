"""
Activity API routes.

Provides endpoints for querying cursor activity data and statistics.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.deps import get_db
from src.api.schemas import (
    ActivityRecord,
    ActivitySummary,
    DailyActivityAggregate,
)
from src.core.db import ChatDatabase

router = APIRouter()


@router.get("/activity", response_model=List[ActivityRecord])
def get_activity(
    start_date: Optional[str] = Query(None, description="Start date (ISO format: YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format: YYYY-MM-DD)"),
    limit: Optional[int] = Query(100, ge=1, le=1000, description="Maximum number of records"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    db: ChatDatabase = Depends(get_db),
):
    """
    Get activity records within a date range.

    Returns a paginated list of activity records sorted by date (newest first).
    """
    try:
        activities = db.get_activity_by_date_range(
            start_date=start_date, end_date=end_date, limit=limit, offset=offset
        )
        return activities
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching activity: {str(e)}")


@router.get("/activity/summary", response_model=ActivitySummary)
def get_activity_summary(
    start_date: Optional[str] = Query(None, description="Start date (ISO format: YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format: YYYY-MM-DD)"),
    db: ChatDatabase = Depends(get_db),
):
    """
    Get aggregated summary statistics for cursor activity.

    Returns total cost, token counts, activity breakdowns, and cost by model.
    """
    try:
        summary = db.get_activity_summary(start_date=start_date, end_date=end_date)
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching summary: {str(e)}")


@router.get("/activity/daily", response_model=List[DailyActivityAggregate])
def get_daily_activity(
    start_date: Optional[str] = Query(None, description="Start date (ISO format: YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format: YYYY-MM-DD)"),
    db: ChatDatabase = Depends(get_db),
):
    """
    Get daily aggregated activity data for charting.

    Returns daily totals for cost, tokens, and activity counts.
    """
    try:
        cursor = db.conn.cursor()

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

        cursor.execute(
            f"""
            SELECT 
                DATE(date) as date,
                COALESCE(SUM(cost), 0) as total_cost,
                COALESCE(SUM(input_tokens_with_cache), 0) as input_with_cache,
                COALESCE(SUM(input_tokens_no_cache), 0) as input_no_cache,
                COALESCE(SUM(cache_read_tokens), 0) as cache_read,
                COALESCE(SUM(output_tokens), 0) as output,
                COALESCE(SUM(total_tokens), 0) as total,
                COUNT(*) as activity_count
            FROM cursor_activity
            {where_clause}
            GROUP BY date
            ORDER BY date ASC
        """,
            params,
        )

        results = []
        for row in cursor.fetchall():
            results.append({
                "date": row[0],
                "total_cost": row[1] or 0.0,
                "input_tokens_with_cache": row[2] or 0,
                "input_tokens_no_cache": row[3] or 0,
                "cache_read_tokens": row[4] or 0,
                "output_tokens": row[5] or 0,
                "total_tokens": row[6] or 0,
                "activity_count": row[7],
            })

        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching daily activity: {str(e)}")
