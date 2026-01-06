"""
Divergence Processing Infrastructure.

Handles batch and background processing of divergence analysis.

Architecture:
- Batch mode: Process all existing chats to backfill divergence scores
- Background mode: Process new/updated chats automatically via polling

Uses the existing ChatDatabase infrastructure with WAL mode for
concurrent read/write access.
"""
import logging
import time
import threading
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime

from src.core.db import ChatDatabase
from .db import DivergenceDatabase
from .segmenter import ConversationSegmenter

logger = logging.getLogger(__name__)


class DivergenceProcessor:
    """
    Orchestrates divergence analysis for batch and background processing.
    
    Provides methods to:
    - Backfill divergence scores for all existing chats
    - Process newly ingested chats automatically
    - Queue specific chats for priority processing
    
    Integrates with the existing ingestion pipeline via hooks.
    
    Attributes
    ----------
    chat_db : ChatDatabase
        Main chat database
    div_db : DivergenceDatabase
        Divergence-specific database layer
    segmenter : ConversationSegmenter
        Ensemble segmenter for analysis
    """
    
    def __init__(
        self,
        chat_db: ChatDatabase,
        use_llm: bool = True,
        llm_model: str = "claude-sonnet-4-20250514",
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        """
        Initialize the processor.
        
        Parameters
        ----------
        chat_db : ChatDatabase
            Main chat database instance
        use_llm : bool
            Whether to use LLM for analysis (default: True)
        llm_model : str
            Claude model for LLM analysis
        embedding_model : str
            Sentence transformer model for embeddings
        """
        self.chat_db = chat_db
        self.div_db = DivergenceDatabase(chat_db.conn)
        self.segmenter = ConversationSegmenter(
            embedding_model=embedding_model,
            use_llm=use_llm,
            llm_model=llm_model,
        )
        self._background_thread = None
        self._stop_background = False
    
    def process_chat(
        self,
        chat_id: int,
        generate_summaries: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single chat for divergence analysis.
        
        Parameters
        ----------
        chat_id : int
            Chat database ID
        generate_summaries : bool
            Whether to generate LLM summaries for segments
            
        Returns
        -------
        dict, optional
            Analysis results or None if chat not found
        """
        # Get chat data
        chat_data = self.chat_db.get_chat(chat_id)
        if not chat_data:
            logger.warning("Chat %d not found", chat_id)
            return None
        
        messages = chat_data.get("messages", [])
        if len(messages) < 2:
            logger.debug("Chat %d has too few messages for analysis", chat_id)
            return None
        
        # Convert messages to expected format
        formatted_messages = [
            {"role": msg.get("role", "user"), "text": msg.get("text", "")}
            for msg in messages
        ]
        
        try:
            # Run full analysis
            report, segments = self.segmenter.analyze_chat_full(
                chat_id=chat_id,
                messages=formatted_messages,
                generate_summaries=generate_summaries,
            )
            
            # Save to database
            self.div_db.save_divergence_report(report)
            
            # Delete old segments and save new ones
            self.div_db.delete_segments(chat_id)
            self.div_db.save_segments(segments)
            
            logger.info(
                "Processed chat %d: score=%.2f, segments=%d",
                chat_id, report.overall_score, len(segments)
            )
            
            return {
                "chat_id": chat_id,
                "overall_score": report.overall_score,
                "num_segments": len(segments),
                "should_split": report.should_split,
                "interpretation": report.interpretation,
            }
            
        except Exception as e:
            logger.error("Error processing chat %d: %s", chat_id, e)
            raise
    
    def backfill_all(
        self,
        batch_size: int = 50,
        min_messages: int = 2,
        max_chats: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        skip_existing: bool = True,
    ) -> Dict[str, int]:
        """
        Backfill divergence scores for all existing chats.
        
        Parameters
        ----------
        batch_size : int
            Number of chats to process before committing
        min_messages : int
            Minimum messages required for analysis
        max_chats : int, optional
            Maximum chats to process (None = all)
        progress_callback : Callable[[int, int], None], optional
            Callback(processed, total) for progress updates
        skip_existing : bool
            Skip chats that already have divergence scores
            
        Returns
        -------
        dict
            Statistics: {"processed": int, "skipped": int, "errors": int}
        """
        logger.info("Starting divergence backfill...")
        
        stats = {"processed": 0, "skipped": 0, "errors": 0}
        
        # Get chats needing processing
        if skip_existing:
            chat_ids = self.div_db.get_chats_without_divergence_score(
                limit=max_chats or 10000,
                min_messages=min_messages,
            )
        else:
            # Get all chats with enough messages
            cursor = self.chat_db.conn.cursor()
            cursor.execute("""
                SELECT id FROM chats 
                WHERE messages_count >= ?
                ORDER BY last_updated_at DESC
                LIMIT ?
            """, (min_messages, max_chats or 10000))
            chat_ids = [row[0] for row in cursor.fetchall()]
        
        total = len(chat_ids)
        logger.info("Found %d chats to process", total)
        
        for i, chat_id in enumerate(chat_ids):
            try:
                result = self.process_chat(chat_id, generate_summaries=False)
                if result:
                    stats["processed"] += 1
                else:
                    stats["skipped"] += 1
                    
            except Exception as e:
                logger.error("Error processing chat %d: %s", chat_id, e)
                stats["errors"] += 1
            
            if progress_callback:
                progress_callback(i + 1, total)
            
            # Log progress periodically
            if (i + 1) % 100 == 0:
                logger.info(
                    "Progress: %d/%d (%.1f%%)",
                    i + 1, total, (i + 1) / total * 100
                )
        
        logger.info(
            "Backfill complete: %d processed, %d skipped, %d errors",
            stats["processed"], stats["skipped"], stats["errors"]
        )
        
        return stats
    
    def process_queue(
        self,
        max_items: Optional[int] = None,
    ) -> Dict[str, int]:
        """
        Process items from the processing queue.
        
        Parameters
        ----------
        max_items : int, optional
            Maximum items to process (None = all pending)
            
        Returns
        -------
        dict
            Statistics: {"processed": int, "errors": int}
        """
        stats = {"processed": 0, "errors": 0}
        items_processed = 0
        
        while True:
            if max_items and items_processed >= max_items:
                break
            
            chat_id = self.div_db.get_next_pending_chat()
            if chat_id is None:
                break
            
            try:
                self.process_chat(chat_id)
                self.div_db.mark_processing_complete(chat_id)
                stats["processed"] += 1
                
            except Exception as e:
                self.div_db.mark_processing_complete(chat_id, error=str(e))
                stats["errors"] += 1
            
            items_processed += 1
        
        return stats
    
    def queue_new_chats(self, since: Optional[datetime] = None) -> int:
        """
        Queue chats that have been updated since a given time.
        
        Parameters
        ----------
        since : datetime, optional
            Queue chats updated after this time. If None, queues all
            chats without divergence scores.
            
        Returns
        -------
        int
            Number of chats queued
        """
        queued = 0
        
        if since:
            chat_ids = self.chat_db.get_chats_updated_since(since)
        else:
            chat_ids = self.div_db.get_chats_without_divergence_score(limit=1000)
        
        for chat_id in chat_ids:
            self.div_db.queue_chat_for_processing(chat_id)
            queued += 1
        
        logger.info("Queued %d chats for processing", queued)
        return queued
    
    def start_background_processing(
        self,
        poll_interval: float = 30.0,
        batch_size: int = 10,
    ) -> None:
        """
        Start background processing thread.
        
        Polls for new chats and processes them automatically.
        
        Parameters
        ----------
        poll_interval : float
            Seconds between polls (default: 30)
        batch_size : int
            Max items to process per poll
        """
        if self._background_thread and self._background_thread.is_alive():
            logger.warning("Background processing already running")
            return
        
        self._stop_background = False
        
        def process_loop():
            logger.info(
                "Starting divergence background processor (interval: %.1fs)",
                poll_interval
            )
            
            last_check = datetime.now()
            
            while not self._stop_background:
                try:
                    # Queue any new chats
                    self.queue_new_chats(since=last_check)
                    last_check = datetime.now()
                    
                    # Process queue
                    stats = self.process_queue(max_items=batch_size)
                    
                    if stats["processed"] > 0:
                        logger.info(
                            "Background: processed %d, errors %d",
                            stats["processed"], stats["errors"]
                        )
                    
                except Exception as e:
                    logger.error("Background processing error: %s", e)
                
                # Sleep with interruptibility
                for _ in range(int(poll_interval)):
                    if self._stop_background:
                        break
                    time.sleep(1)
        
        self._background_thread = threading.Thread(
            target=process_loop,
            daemon=True,
            name="DivergenceProcessor"
        )
        self._background_thread.start()
        logger.info("Background divergence processor started")
    
    def stop_background_processing(self) -> None:
        """Stop background processing thread."""
        self._stop_background = True
        if self._background_thread:
            self._background_thread.join(timeout=5)
            logger.info("Background divergence processor stopped")
    
    def is_background_running(self) -> bool:
        """Check if background processing is active."""
        return (
            self._background_thread is not None and
            self._background_thread.is_alive()
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get processing statistics.
        
        Returns
        -------
        dict
            Statistics including queue status and counts
        """
        cursor = self.chat_db.conn.cursor()
        
        # Total chats
        cursor.execute("SELECT COUNT(*) FROM chats WHERE messages_count >= 2")
        total_chats = cursor.fetchone()[0]
        
        # Chats with divergence scores
        cursor.execute("SELECT COUNT(*) FROM divergence_scores")
        processed_chats = cursor.fetchone()[0]
        
        # High divergence chats
        cursor.execute("""
            SELECT COUNT(*) FROM divergence_scores
            WHERE overall_score >= 0.5
        """)
        high_divergence = cursor.fetchone()[0]
        
        # Queue stats
        queue_stats = self.div_db.get_queue_stats()
        
        return {
            "total_chats": total_chats,
            "processed_chats": processed_chats,
            "unprocessed_chats": total_chats - processed_chats,
            "high_divergence_chats": high_divergence,
            "queue": queue_stats,
            "background_running": self.is_background_running(),
        }
    
    def find_related_chats(
        self,
        chat_id: int,
        min_similarity: float = 0.5,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find chats related to a given chat via segment similarity.
        
        Parameters
        ----------
        chat_id : int
            Source chat ID
        min_similarity : float
            Minimum similarity threshold
        limit : int
            Maximum results
            
        Returns
        -------
        list[dict]
            Related chats with similarity scores
        """
        # Get segments for source chat
        segments = self.div_db.get_segments(chat_id)
        if not segments:
            return []
        
        # Find similar segments across other chats
        all_similar = []
        seen_chats = {chat_id}
        
        for segment in segments:
            similar = self.div_db.find_similar_segments(
                segment_id=segment.id,
                min_similarity=min_similarity,
                limit=limit,
                exclude_same_chat=True,
            )
            
            for s in similar:
                if s["chat_id"] not in seen_chats:
                    all_similar.append(s)
                    seen_chats.add(s["chat_id"])
        
        # Sort by similarity and get chat details
        all_similar.sort(key=lambda x: x["similarity"], reverse=True)
        results = []
        
        for item in all_similar[:limit]:
            chat_data = self.chat_db.get_chat(item["chat_id"])
            if chat_data:
                results.append({
                    "chat_id": item["chat_id"],
                    "title": chat_data.get("title", "Untitled"),
                    "similarity": item["similarity"],
                    "matching_topic": item.get("topic_label") or item.get("summary", ""),
                })
        
        return results


class DivergenceProcessorIntegration:
    """
    Integration helper for connecting to existing infrastructure.
    
    Provides hooks for the ingestion pipeline to automatically
    queue chats for divergence processing.
    """
    
    @staticmethod
    def create_ingestion_callback(processor: DivergenceProcessor):
        """
        Create a callback for the ingestion pipeline.
        
        Returns a function that can be called after each chat is ingested
        to queue it for divergence processing.
        
        Parameters
        ----------
        processor : DivergenceProcessor
            The processor instance to use
            
        Returns
        -------
        Callable[[int], None]
            Callback function that takes chat_id
        """
        def callback(chat_id: int):
            try:
                processor.div_db.queue_chat_for_processing(chat_id, priority=1)
            except Exception as e:
                logger.warning("Failed to queue chat %d: %s", chat_id, e)
        
        return callback
    
    @staticmethod
    def create_watcher_callback(processor: DivergenceProcessor):
        """
        Create a callback for the file watcher.
        
        Returns a function that processes the queue when changes are detected.
        
        Parameters
        ----------
        processor : DivergenceProcessor
            The processor instance to use
            
        Returns
        -------
        Callable[[], None]
            Callback function for the watcher
        """
        def callback():
            try:
                # Queue any new chats and process
                processor.queue_new_chats()
                processor.process_queue(max_items=20)
            except Exception as e:
                logger.error("Watcher callback error: %s", e)
        
        return callback
