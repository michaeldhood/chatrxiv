"""
Ingestion state repository for tracking data ingestion progress.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseRepository


class IngestionStateRepository(BaseRepository):
    """
    Repository for ingestion state tracking.

    Handles incremental ingestion checkpoints and statistics.
    """

    def get_state(self, source: str = "cursor") -> Optional[Dict[str, Any]]:
        """
        Get ingestion state for a source.

        Parameters
        ----------
        source : str
            Source name (e.g., "cursor", "claude")

        Returns
        -------
        Optional[Dict[str, Any]]
            Ingestion state or None if not found
        """
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT last_run_at, last_processed_timestamp, last_composer_id,
                   stats_ingested, stats_skipped, stats_errors
            FROM ingestion_state
            WHERE source = ?
        """,
            (source,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        return {
            "last_run_at": row[0],
            "last_processed_timestamp": row[1],
            "last_composer_id": row[2],
            "stats_ingested": row[3] or 0,
            "stats_skipped": row[4] or 0,
            "stats_errors": row[5] or 0,
        }

    def update_state(
        self,
        source: str,
        last_run_at: Optional[datetime] = None,
        last_processed_timestamp: Optional[str] = None,
        last_composer_id: Optional[str] = None,
        stats: Optional[Dict[str, int]] = None,
    ) -> None:
        """
        Update ingestion state for a source.

        Parameters
        ----------
        source : str
            Source name
        last_run_at : datetime, optional
            When ingestion last ran
        last_processed_timestamp : str, optional
            Last processed timestamp (ISO format)
        last_composer_id : str, optional
            Last processed composer ID
        stats : Dict[str, int], optional
            Statistics from last run
        """
        cursor = self.cursor()

        # Check if exists
        cursor.execute(
            "SELECT source FROM ingestion_state WHERE source = ?", (source,)
        )
        exists = cursor.fetchone() is not None

        if exists:
            # Update
            updates = []
            params = []

            if last_run_at is not None:
                updates.append("last_run_at = ?")
                params.append(last_run_at.isoformat())

            if last_processed_timestamp is not None:
                updates.append("last_processed_timestamp = ?")
                params.append(last_processed_timestamp)

            if last_composer_id is not None:
                updates.append("last_composer_id = ?")
                params.append(last_composer_id)

            if stats:
                if "ingested" in stats:
                    updates.append("stats_ingested = ?")
                    params.append(stats["ingested"])
                if "skipped" in stats:
                    updates.append("stats_skipped = ?")
                    params.append(stats["skipped"])
                if "errors" in stats:
                    updates.append("stats_errors = ?")
                    params.append(stats["errors"])

            if updates:
                params.append(source)
                cursor.execute(
                    f"UPDATE ingestion_state SET {', '.join(updates)} WHERE source = ?",
                    params,
                )
        else:
            # Insert
            cursor.execute(
                """
                INSERT INTO ingestion_state
                (source, last_run_at, last_processed_timestamp, last_composer_id,
                 stats_ingested, stats_skipped, stats_errors)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    source,
                    last_run_at.isoformat() if last_run_at else None,
                    last_processed_timestamp,
                    last_composer_id,
                    stats.get("ingested", 0) if stats else 0,
                    stats.get("skipped", 0) if stats else 0,
                    stats.get("errors", 0) if stats else 0,
                ),
            )

        self.commit()

    def get_chats_updated_since(
        self, timestamp: datetime, source: str = "cursor"
    ) -> List[str]:
        """
        Get composer IDs of chats updated since a timestamp.

        Useful for incremental ingestion - only process chats that have been updated.

        Parameters
        ----------
        timestamp : datetime
            Timestamp to compare against
        source : str
            Source filter (e.g., "cursor")

        Returns
        -------
        List[str]
            List of composer IDs
        """
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT cursor_composer_id
            FROM chats
            WHERE source = ? AND last_updated_at > ?
            ORDER BY last_updated_at ASC
        """,
            (source, timestamp.isoformat()),
        )

        return [row[0] for row in cursor.fetchall()]
