"""
Repository for topic analysis segments and divergence data.

Handles CRUD operations for chat_topic_analysis, chat_segments,
chat_message_judgements, and segment_links tables.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base import BaseRepository

logger = logging.getLogger(__name__)


class SegmentRepository(BaseRepository):
    """
    Repository for topic divergence analysis and chat segmentation data.

    Manages four tables:
    - chat_topic_analysis: per-chat divergence reports
    - chat_segments: segment records within a chat
    - chat_message_judgements: LLM per-message classifications
    - segment_links: cross-segment relationships
    """

    def upsert_topic_analysis(
        self,
        chat_id: int,
        report: Dict[str, Any],
        segments: List[Dict[str, Any]],
        judgement_rows: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Store or update a complete topic analysis for a chat.

        Atomically replaces all analysis data (report, segments, judgements)
        for the given chat_id in a single transaction.

        Parameters
        ----------
        chat_id : int
            The chat to store analysis for.
        report : dict
            Divergence report containing scores and metadata.
        segments : list of dict
            Segment records with start/end indices, labels, summaries.
        judgement_rows : list of dict, optional
            LLM per-message judgements (only when LLM is enabled).
        """
        cursor = self.cursor()
        try:
            now = datetime.now(timezone.utc).isoformat()

            # Upsert the analysis report
            cursor.execute(
                """
                INSERT OR REPLACE INTO chat_topic_analysis (
                    chat_id, computed_at, source_last_updated_at, analysis_version,
                    overall_score, embedding_drift_score, topic_entropy_score,
                    topic_transition_score, llm_relevance_score,
                    num_segments, should_split, suggested_split_points,
                    topic_summaries, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    now,
                    report.get("source_last_updated_at"),
                    report.get("analysis_version", 1),
                    report.get("overall_score", 0.0),
                    report.get("embedding_drift_score", 0.0),
                    report.get("topic_entropy_score", 0.0),
                    report.get("topic_transition_score", 0.0),
                    report.get("llm_relevance_score"),
                    len(segments),
                    1 if report.get("should_split", False) else 0,
                    json.dumps(report.get("suggested_split_points", [])),
                    json.dumps(report.get("topic_summaries", [])),
                    json.dumps(report.get("raw_json")) if report.get("raw_json") else None,
                ),
            )

            # Replace segments: delete old, insert new
            cursor.execute("DELETE FROM chat_segments WHERE chat_id = ?", (chat_id,))
            for seg in segments:
                cursor.execute(
                    """
                    INSERT INTO chat_segments (
                        chat_id, start_message_idx, end_message_idx,
                        parent_segment_id, topic_label, summary,
                        divergence_score, anchor_embedding
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chat_id,
                        seg["start_message_idx"],
                        seg["end_message_idx"],
                        seg.get("parent_segment_id"),
                        seg.get("topic_label"),
                        seg.get("summary"),
                        seg.get("divergence_score", 0.0),
                        json.dumps(seg["anchor_embedding"]) if seg.get("anchor_embedding") else None,
                    ),
                )

            # Replace judgements if provided
            cursor.execute("DELETE FROM chat_message_judgements WHERE chat_id = ?", (chat_id,))
            if judgement_rows:
                for j in judgement_rows:
                    cursor.execute(
                        """
                        INSERT INTO chat_message_judgements (
                            chat_id, message_idx, relation,
                            relevance_score, suggested_segment_break, reasoning
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            chat_id,
                            j["message_idx"],
                            j.get("relation"),
                            j.get("relevance_score"),
                            1 if j.get("suggested_segment_break", False) else 0,
                            j.get("reasoning"),
                        ),
                    )

            self.commit()
            logger.debug(
                "Stored topic analysis for chat %d: score=%.2f, %d segments",
                chat_id,
                report.get("overall_score", 0.0),
                len(segments),
            )
        except Exception:
            self.rollback()
            raise

    def get_topic_analysis(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Get stored topic analysis for a chat.

        Parameters
        ----------
        chat_id : int
            Chat ID to look up.

        Returns
        -------
        dict or None
            Analysis report dict, or None if no analysis exists.
        """
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT chat_id, computed_at, source_last_updated_at, analysis_version,
                   overall_score, embedding_drift_score, topic_entropy_score,
                   topic_transition_score, llm_relevance_score,
                   num_segments, should_split, suggested_split_points,
                   topic_summaries, raw_json
            FROM chat_topic_analysis
            WHERE chat_id = ?
            """,
            (chat_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "chat_id": row[0],
            "computed_at": row[1],
            "source_last_updated_at": row[2],
            "analysis_version": row[3],
            "overall_score": row[4],
            "embedding_drift_score": row[5],
            "topic_entropy_score": row[6],
            "topic_transition_score": row[7],
            "llm_relevance_score": row[8],
            "num_segments": row[9],
            "should_split": bool(row[10]),
            "suggested_split_points": json.loads(row[11]) if row[11] else [],
            "topic_summaries": json.loads(row[12]) if row[12] else [],
            "raw_json": json.loads(row[13]) if row[13] else None,
        }

    def get_chat_segments(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        Get all segments for a chat, ordered by start index.

        Parameters
        ----------
        chat_id : int
            Chat ID.

        Returns
        -------
        list of dict
            Segment records.
        """
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT id, chat_id, start_message_idx, end_message_idx,
                   parent_segment_id, topic_label, summary,
                   divergence_score, anchor_embedding, created_at
            FROM chat_segments
            WHERE chat_id = ?
            ORDER BY start_message_idx
            """,
            (chat_id,),
        )
        return [
            {
                "id": row[0],
                "chat_id": row[1],
                "start_message_idx": row[2],
                "end_message_idx": row[3],
                "parent_segment_id": row[4],
                "topic_label": row[5],
                "summary": row[6],
                "divergence_score": row[7],
                "anchor_embedding": json.loads(row[8]) if row[8] else None,
                "created_at": row[9],
            }
            for row in cursor.fetchall()
        ]

    def get_message_judgements(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        Get LLM judgements for a chat's messages.

        Parameters
        ----------
        chat_id : int
            Chat ID.

        Returns
        -------
        list of dict
            Judgement records ordered by message index.
        """
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT chat_id, message_idx, relation, relevance_score,
                   suggested_segment_break, reasoning, created_at
            FROM chat_message_judgements
            WHERE chat_id = ?
            ORDER BY message_idx
            """,
            (chat_id,),
        )
        return [
            {
                "chat_id": row[0],
                "message_idx": row[1],
                "relation": row[2],
                "relevance_score": row[3],
                "suggested_segment_break": bool(row[4]),
                "reasoning": row[5],
                "created_at": row[6],
            }
            for row in cursor.fetchall()
        ]

    def list_chats_needing_topic_analysis(
        self,
        incremental: bool = True,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Find chats that need (re-)analysis.

        When incremental=True, returns only chats where:
        - No analysis exists, OR
        - Chat was updated since last analysis (source_last_updated_at mismatch)

        Parameters
        ----------
        incremental : bool
            If True, only return chats needing update. If False, return all.
        limit : int
            Maximum number of chats to return.

        Returns
        -------
        list of dict
            Chat records with id, last_updated_at, messages_count.
        """
        cursor = self.cursor()

        if incremental:
            cursor.execute(
                """
                SELECT c.id, c.last_updated_at, c.messages_count
                FROM chats c
                LEFT JOIN chat_topic_analysis ta ON c.id = ta.chat_id
                WHERE c.messages_count > 0
                  AND (
                    ta.chat_id IS NULL
                    OR ta.source_last_updated_at IS NULL
                    OR ta.source_last_updated_at != c.last_updated_at
                  )
                ORDER BY c.last_updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
        else:
            cursor.execute(
                """
                SELECT c.id, c.last_updated_at, c.messages_count
                FROM chats c
                WHERE c.messages_count > 0
                ORDER BY c.last_updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )

        return [
            {
                "id": row[0],
                "last_updated_at": row[1],
                "messages_count": row[2],
            }
            for row in cursor.fetchall()
        ]

    def upsert_segment_link(
        self,
        source_segment_id: int,
        target_segment_id: int,
        link_type: str,
        similarity: Optional[float] = None,
    ) -> int:
        """
        Create or update a cross-segment link.

        Parameters
        ----------
        source_segment_id : int
            Source segment ID.
        target_segment_id : int
            Target segment ID.
        link_type : str
            Relationship type (continues, references, branches_from, resolves).
        similarity : float, optional
            Similarity score between segments.

        Returns
        -------
        int
            Link record ID.
        """
        cursor = self.cursor()

        # Check for existing link
        cursor.execute(
            """
            SELECT id FROM segment_links
            WHERE source_segment_id = ? AND target_segment_id = ? AND link_type = ?
            """,
            (source_segment_id, target_segment_id, link_type),
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                "UPDATE segment_links SET similarity = ? WHERE id = ?",
                (similarity, existing[0]),
            )
            self.commit()
            return existing[0]
        else:
            cursor.execute(
                """
                INSERT INTO segment_links (source_segment_id, target_segment_id, link_type, similarity)
                VALUES (?, ?, ?, ?)
                """,
                (source_segment_id, target_segment_id, link_type, similarity),
            )
            self.commit()
            return cursor.lastrowid

    def get_high_divergence_chats(
        self,
        threshold: float = 0.5,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        List chats with divergence scores above a threshold.

        Parameters
        ----------
        threshold : float
            Minimum divergence score.
        limit : int
            Maximum results.

        Returns
        -------
        list of dict
            Analysis records with chat info.
        """
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT ta.chat_id, ta.overall_score, ta.num_segments, ta.should_split,
                   ta.computed_at, c.title, c.messages_count
            FROM chat_topic_analysis ta
            JOIN chats c ON ta.chat_id = c.id
            WHERE ta.overall_score >= ?
            ORDER BY ta.overall_score DESC
            LIMIT ?
            """,
            (threshold, limit),
        )
        return [
            {
                "chat_id": row[0],
                "overall_score": row[1],
                "num_segments": row[2],
                "should_split": bool(row[3]),
                "computed_at": row[4],
                "title": row[5],
                "messages_count": row[6],
            }
            for row in cursor.fetchall()
        ]

    def get_stats(self) -> Dict[str, Any]:
        """
        Get summary statistics for topic analysis.

        Returns
        -------
        dict
            Stats including total analyzed, score distribution, etc.
        """
        cursor = self.cursor()

        cursor.execute("SELECT COUNT(*) FROM chat_topic_analysis")
        total_analyzed = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM chats WHERE messages_count > 0")
        total_chats = cursor.fetchone()[0]

        cursor.execute("SELECT AVG(overall_score) FROM chat_topic_analysis")
        avg_score_row = cursor.fetchone()
        avg_score = avg_score_row[0] if avg_score_row[0] is not None else 0.0

        cursor.execute("SELECT SUM(num_segments) FROM chat_topic_analysis")
        total_segments_row = cursor.fetchone()
        total_segments = total_segments_row[0] if total_segments_row[0] is not None else 0

        cursor.execute(
            "SELECT COUNT(*) FROM chat_topic_analysis WHERE should_split = 1"
        )
        should_split_count = cursor.fetchone()[0]

        # Score distribution buckets
        buckets = {}
        for label, low, high in [
            ("highly_focused", 0.0, 0.2),
            ("mostly_focused", 0.2, 0.4),
            ("moderate_divergence", 0.4, 0.6),
            ("significant_divergence", 0.6, 0.8),
            ("highly_divergent", 0.8, 1.01),
        ]:
            cursor.execute(
                "SELECT COUNT(*) FROM chat_topic_analysis WHERE overall_score >= ? AND overall_score < ?",
                (low, high),
            )
            buckets[label] = cursor.fetchone()[0]

        return {
            "total_chats": total_chats,
            "total_analyzed": total_analyzed,
            "pending_analysis": total_chats - total_analyzed,
            "avg_score": round(avg_score, 3),
            "total_segments": total_segments,
            "should_split_count": should_split_count,
            "score_distribution": buckets,
        }
