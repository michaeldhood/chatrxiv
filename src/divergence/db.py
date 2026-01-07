"""
Database extensions for divergence detection.

Adds tables and methods for storing segments, segment links,
and divergence scores.
"""
import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np

from .models import Segment, SegmentLink, DivergenceReport, DivergenceMetrics, LinkType

logger = logging.getLogger(__name__)


class DivergenceDatabase:
    """
    Database layer for divergence detection data.
    
    Extends the main chat database with tables for:
    - segments: Topic segments within chats
    - segment_embeddings: Stored embeddings for segments
    - segment_links: Relationships between segments
    - divergence_scores: Computed divergence scores per chat
    - divergence_processing_queue: Queue for batch processing
    """
    
    def __init__(self, conn: sqlite3.Connection):
        """
        Initialize with existing database connection.
        
        Parameters
        ----------
        conn : sqlite3.Connection
            Connection to the chat database (from ChatDatabase)
        """
        self.conn = conn
        self._ensure_schema()
    
    def _ensure_schema(self):
        """Create divergence-related tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Segments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS segments (
                id TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                start_message_idx INTEGER NOT NULL,
                end_message_idx INTEGER NOT NULL,
                summary TEXT,
                topic_label TEXT,
                parent_segment_id TEXT,
                divergence_score REAL DEFAULT 0.0,
                created_at TEXT,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_segment_id) REFERENCES segments(id) ON DELETE SET NULL
            )
        """)
        
        # Segment embeddings (stored as blob for efficiency)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS segment_embeddings (
                segment_id TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                embedding_dim INTEGER NOT NULL,
                model_name TEXT,
                created_at TEXT,
                FOREIGN KEY (segment_id) REFERENCES segments(id) ON DELETE CASCADE
            )
        """)
        
        # Segment links
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS segment_links (
                id TEXT PRIMARY KEY,
                source_segment_id TEXT NOT NULL,
                target_segment_id TEXT NOT NULL,
                link_type TEXT NOT NULL,
                similarity_score REAL DEFAULT 0.0,
                created_at TEXT,
                metadata TEXT,
                FOREIGN KEY (source_segment_id) REFERENCES segments(id) ON DELETE CASCADE,
                FOREIGN KEY (target_segment_id) REFERENCES segments(id) ON DELETE CASCADE
            )
        """)
        
        # Divergence scores per chat
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS divergence_scores (
                chat_id INTEGER PRIMARY KEY,
                overall_score REAL NOT NULL,
                embedding_drift_score REAL,
                topic_entropy_score REAL,
                topic_transition_score REAL,
                llm_relevance_score REAL,
                metrics_json TEXT,
                num_segments INTEGER DEFAULT 1,
                should_split INTEGER DEFAULT 0,
                suggested_split_points TEXT,
                interpretation TEXT,
                computed_at TEXT,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)
        
        # Processing queue for batch/background processing
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS divergence_processing_queue (
                chat_id INTEGER PRIMARY KEY,
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                queued_at TEXT,
                started_at TEXT,
                completed_at TEXT,
                error_message TEXT,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)
        
        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_segments_chat 
            ON segments(chat_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_segments_parent 
            ON segments(parent_segment_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_segment_links_source 
            ON segment_links(source_segment_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_segment_links_target 
            ON segment_links(target_segment_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_divergence_queue_status 
            ON divergence_processing_queue(status, priority DESC)
        """)
        
        self.conn.commit()
        logger.debug("Divergence schema initialized")
    
    # ==================== Segment Operations ====================
    
    def save_segment(self, segment: Segment) -> None:
        """
        Save or update a segment.
        
        Parameters
        ----------
        segment : Segment
            Segment to save
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO segments 
            (id, chat_id, start_message_idx, end_message_idx, summary, 
             topic_label, parent_segment_id, divergence_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            segment.id,
            segment.chat_id,
            segment.start_message_idx,
            segment.end_message_idx,
            segment.summary,
            segment.topic_label,
            segment.parent_segment_id,
            segment.divergence_score,
            segment.created_at.isoformat() if segment.created_at else datetime.now().isoformat(),
        ))
        
        # Save embedding if present
        if segment.anchor_embedding is not None:
            self._save_embedding(segment.id, segment.anchor_embedding)
        
        self.conn.commit()
    
    def save_segments(self, segments: List[Segment]) -> None:
        """
        Save multiple segments in a batch.
        
        Parameters
        ----------
        segments : List[Segment]
            Segments to save
        """
        cursor = self.conn.cursor()
        
        for segment in segments:
            cursor.execute("""
                INSERT OR REPLACE INTO segments 
                (id, chat_id, start_message_idx, end_message_idx, summary, 
                 topic_label, parent_segment_id, divergence_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                segment.id,
                segment.chat_id,
                segment.start_message_idx,
                segment.end_message_idx,
                segment.summary,
                segment.topic_label,
                segment.parent_segment_id,
                segment.divergence_score,
                segment.created_at.isoformat() if segment.created_at else datetime.now().isoformat(),
            ))
            
            if segment.anchor_embedding is not None:
                self._save_embedding(segment.id, segment.anchor_embedding)
        
        self.conn.commit()
    
    def _save_embedding(
        self,
        segment_id: str,
        embedding: np.ndarray,
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        """Save embedding as blob."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO segment_embeddings
            (segment_id, embedding, embedding_dim, model_name, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            segment_id,
            embedding.astype(np.float32).tobytes(),
            len(embedding),
            model_name,
            datetime.now().isoformat(),
        ))
    
    def get_segments(self, chat_id: int) -> List[Segment]:
        """
        Get all segments for a chat.
        
        Parameters
        ----------
        chat_id : int
            Chat database ID
            
        Returns
        -------
        List[Segment]
            Segments ordered by start index
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT s.id, s.chat_id, s.start_message_idx, s.end_message_idx,
                   s.summary, s.topic_label, s.parent_segment_id, 
                   s.divergence_score, s.created_at,
                   e.embedding, e.embedding_dim
            FROM segments s
            LEFT JOIN segment_embeddings e ON s.id = e.segment_id
            WHERE s.chat_id = ?
            ORDER BY s.start_message_idx
        """, (chat_id,))
        
        segments = []
        for row in cursor.fetchall():
            # Reconstruct embedding if present
            embedding = None
            if row[9] is not None:
                embedding = np.frombuffer(row[9], dtype=np.float32)
            
            created_at = None
            if row[8]:
                try:
                    created_at = datetime.fromisoformat(row[8])
                except ValueError:
                    pass
            
            segment = Segment(
                id=row[0],
                chat_id=row[1],
                start_message_idx=row[2],
                end_message_idx=row[3],
                anchor_embedding=embedding,
                summary=row[4] or "",
                topic_label=row[5],
                parent_segment_id=row[6],
                divergence_score=row[7] or 0.0,
                created_at=created_at,
            )
            segments.append(segment)
        
        return segments
    
    def get_segment(self, segment_id: str) -> Optional[Segment]:
        """Get a single segment by ID."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT s.id, s.chat_id, s.start_message_idx, s.end_message_idx,
                   s.summary, s.topic_label, s.parent_segment_id, 
                   s.divergence_score, s.created_at,
                   e.embedding, e.embedding_dim
            FROM segments s
            LEFT JOIN segment_embeddings e ON s.id = e.segment_id
            WHERE s.id = ?
        """, (segment_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        embedding = None
        if row[9] is not None:
            embedding = np.frombuffer(row[9], dtype=np.float32)
        
        return Segment(
            id=row[0],
            chat_id=row[1],
            start_message_idx=row[2],
            end_message_idx=row[3],
            anchor_embedding=embedding,
            summary=row[4] or "",
            topic_label=row[5],
            parent_segment_id=row[6],
            divergence_score=row[7] or 0.0,
        )
    
    def delete_segments(self, chat_id: int) -> int:
        """
        Delete all segments for a chat.
        
        Returns number of segments deleted.
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM segments WHERE chat_id = ?", (chat_id,))
        deleted = cursor.rowcount
        self.conn.commit()
        return deleted
    
    # ==================== Segment Link Operations ====================
    
    def save_link(self, link: SegmentLink) -> None:
        """Save a segment link."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO segment_links
            (id, source_segment_id, target_segment_id, link_type,
             similarity_score, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            link.id,
            link.source_segment_id,
            link.target_segment_id,
            link.link_type.value,
            link.similarity_score,
            link.created_at.isoformat() if link.created_at else datetime.now().isoformat(),
            json.dumps(link.metadata) if link.metadata else None,
        ))
        
        self.conn.commit()
    
    def get_links_from_segment(self, segment_id: str) -> List[SegmentLink]:
        """Get all links originating from a segment."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT id, source_segment_id, target_segment_id, link_type,
                   similarity_score, created_at, metadata
            FROM segment_links
            WHERE source_segment_id = ?
        """, (segment_id,))
        
        links = []
        for row in cursor.fetchall():
            links.append(SegmentLink(
                id=row[0],
                source_segment_id=row[1],
                target_segment_id=row[2],
                link_type=LinkType(row[3]),
                similarity_score=row[4] or 0.0,
                created_at=datetime.fromisoformat(row[5]) if row[5] else None,
                metadata=json.loads(row[6]) if row[6] else None,
            ))
        
        return links
    
    def get_links_to_segment(self, segment_id: str) -> List[SegmentLink]:
        """Get all links pointing to a segment."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT id, source_segment_id, target_segment_id, link_type,
                   similarity_score, created_at, metadata
            FROM segment_links
            WHERE target_segment_id = ?
        """, (segment_id,))
        
        links = []
        for row in cursor.fetchall():
            links.append(SegmentLink(
                id=row[0],
                source_segment_id=row[1],
                target_segment_id=row[2],
                link_type=LinkType(row[3]),
                similarity_score=row[4] or 0.0,
                metadata=json.loads(row[6]) if row[6] else None,
            ))
        
        return links
    
    # ==================== Divergence Score Operations ====================
    
    def save_divergence_report(self, report: DivergenceReport) -> None:
        """
        Save a divergence report for a chat.
        
        Parameters
        ----------
        report : DivergenceReport
            Report to save
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO divergence_scores
            (chat_id, overall_score, embedding_drift_score, topic_entropy_score,
             topic_transition_score, llm_relevance_score, metrics_json,
             num_segments, should_split, suggested_split_points,
             interpretation, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report.chat_id,
            report.overall_score,
            report.embedding_drift_score,
            report.topic_entropy_score,
            report.topic_transition_score,
            report.llm_relevance_score,
            json.dumps(report.metrics.to_dict()),
            report.num_segments,
            1 if report.should_split else 0,
            json.dumps(report.suggested_split_points),
            report.interpretation,
            report.computed_at.isoformat() if report.computed_at else datetime.now().isoformat(),
        ))
        
        self.conn.commit()
    
    def get_divergence_report(self, chat_id: int) -> Optional[DivergenceReport]:
        """
        Get divergence report for a chat.
        
        Parameters
        ----------
        chat_id : int
            Chat database ID
            
        Returns
        -------
        DivergenceReport, optional
            Report or None if not computed
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT chat_id, overall_score, embedding_drift_score, topic_entropy_score,
                   topic_transition_score, llm_relevance_score, metrics_json,
                   num_segments, should_split, suggested_split_points,
                   interpretation, computed_at
            FROM divergence_scores
            WHERE chat_id = ?
        """, (chat_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        # Reconstruct metrics
        metrics_dict = json.loads(row[6]) if row[6] else {}
        metrics = DivergenceMetrics(**metrics_dict)
        
        return DivergenceReport(
            chat_id=row[0],
            overall_score=row[1],
            embedding_drift_score=row[2],
            topic_entropy_score=row[3],
            topic_transition_score=row[4],
            llm_relevance_score=row[5],
            metrics=metrics,
            num_segments=row[7] or 1,
            should_split=bool(row[8]),
            suggested_split_points=json.loads(row[9]) if row[9] else [],
            interpretation=row[10] or "",
            computed_at=datetime.fromisoformat(row[11]) if row[11] else None,
        )
    
    def get_chats_without_divergence_score(
        self,
        limit: int = 100,
        min_messages: int = 2,
    ) -> List[int]:
        """
        Get chat IDs that need divergence analysis.
        
        Parameters
        ----------
        limit : int
            Maximum number to return
        min_messages : int
            Minimum messages required for analysis
            
        Returns
        -------
        List[int]
            Chat IDs without divergence scores
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT c.id
            FROM chats c
            LEFT JOIN divergence_scores d ON c.id = d.chat_id
            WHERE d.chat_id IS NULL
            AND c.messages_count >= ?
            ORDER BY c.last_updated_at DESC
            LIMIT ?
        """, (min_messages, limit))
        
        return [row[0] for row in cursor.fetchall()]
    
    def get_high_divergence_chats(
        self,
        threshold: float = 0.5,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get chats with high divergence scores.
        
        Useful for identifying chats that might need to be split.
        
        Parameters
        ----------
        threshold : float
            Minimum divergence score
        limit : int
            Maximum number to return
            
        Returns
        -------
        List[Dict[str, Any]]
            Chats with their divergence info
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT c.id, c.title, c.messages_count, 
                   d.overall_score, d.num_segments, d.should_split,
                   d.interpretation
            FROM chats c
            INNER JOIN divergence_scores d ON c.id = d.chat_id
            WHERE d.overall_score >= ?
            ORDER BY d.overall_score DESC
            LIMIT ?
        """, (threshold, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "chat_id": row[0],
                "title": row[1],
                "messages_count": row[2],
                "overall_score": row[3],
                "num_segments": row[4],
                "should_split": bool(row[5]),
                "interpretation": row[6],
            })
        
        return results
    
    # ==================== Processing Queue Operations ====================
    
    def queue_chat_for_processing(
        self,
        chat_id: int,
        priority: int = 0,
    ) -> None:
        """
        Add a chat to the processing queue.
        
        Parameters
        ----------
        chat_id : int
            Chat to process
        priority : int
            Higher = process sooner (default: 0)
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO divergence_processing_queue
            (chat_id, status, priority, queued_at)
            VALUES (?, 'pending', ?, ?)
        """, (chat_id, priority, datetime.now().isoformat()))
        
        self.conn.commit()
    
    def get_next_pending_chat(self) -> Optional[int]:
        """
        Get the next chat to process from the queue.
        
        Returns
        -------
        int, optional
            Chat ID or None if queue is empty
        """
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT chat_id
            FROM divergence_processing_queue
            WHERE status = 'pending'
            ORDER BY priority DESC, queued_at ASC
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        if row:
            # Mark as processing
            cursor.execute("""
                UPDATE divergence_processing_queue
                SET status = 'processing', started_at = ?
                WHERE chat_id = ?
            """, (datetime.now().isoformat(), row[0]))
            self.conn.commit()
            return row[0]
        
        return None
    
    def mark_processing_complete(
        self,
        chat_id: int,
        error: Optional[str] = None,
    ) -> None:
        """
        Mark a chat as processed (success or failure).
        
        Parameters
        ----------
        chat_id : int
            Chat that was processed
        error : str, optional
            Error message if processing failed
        """
        cursor = self.conn.cursor()
        
        if error:
            cursor.execute("""
                UPDATE divergence_processing_queue
                SET status = 'failed', completed_at = ?, error_message = ?
                WHERE chat_id = ?
            """, (datetime.now().isoformat(), error, chat_id))
        else:
            cursor.execute("""
                UPDATE divergence_processing_queue
                SET status = 'completed', completed_at = ?
                WHERE chat_id = ?
            """, (datetime.now().isoformat(), chat_id))
        
        self.conn.commit()
    
    def get_queue_stats(self) -> Dict[str, int]:
        """Get processing queue statistics."""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM divergence_processing_queue
            GROUP BY status
        """)
        
        stats = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
        for row in cursor.fetchall():
            stats[row[0]] = row[1]
        
        return stats
    
    def clear_completed_queue(self) -> int:
        """
        Clear completed entries from the queue.
        
        Returns number of entries cleared.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            DELETE FROM divergence_processing_queue
            WHERE status = 'completed'
        """)
        deleted = cursor.rowcount
        self.conn.commit()
        return deleted
    
    # ==================== Cross-Chat Linking ====================
    
    def find_similar_segments(
        self,
        segment_id: str,
        min_similarity: float = 0.5,
        limit: int = 10,
        exclude_same_chat: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Find segments similar to a given segment using stored embeddings.
        
        Parameters
        ----------
        segment_id : str
            Source segment ID
        min_similarity : float
            Minimum cosine similarity threshold
        limit : int
            Maximum results
        exclude_same_chat : bool
            Whether to exclude segments from the same chat
            
        Returns
        -------
        List[Dict[str, Any]]
            Similar segments with similarity scores
        """
        # Get source embedding
        source = self.get_segment(segment_id)
        if source is None or source.anchor_embedding is None:
            return []
        
        cursor = self.conn.cursor()
        
        # Get all segment embeddings
        if exclude_same_chat:
            cursor.execute("""
                SELECT s.id, s.chat_id, s.summary, s.topic_label,
                       e.embedding, e.embedding_dim
                FROM segments s
                INNER JOIN segment_embeddings e ON s.id = e.segment_id
                WHERE s.chat_id != ?
            """, (source.chat_id,))
        else:
            cursor.execute("""
                SELECT s.id, s.chat_id, s.summary, s.topic_label,
                       e.embedding, e.embedding_dim
                FROM segments s
                INNER JOIN segment_embeddings e ON s.id = e.segment_id
                WHERE s.id != ?
            """, (segment_id,))
        
        results = []
        for row in cursor.fetchall():
            target_embedding = np.frombuffer(row[4], dtype=np.float32)
            
            # Compute cosine similarity
            similarity = float(np.dot(source.anchor_embedding, target_embedding))
            
            if similarity >= min_similarity:
                results.append({
                    "segment_id": row[0],
                    "chat_id": row[1],
                    "summary": row[2],
                    "topic_label": row[3],
                    "similarity": similarity,
                })
        
        # Sort by similarity and limit
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]
