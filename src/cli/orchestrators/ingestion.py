"""
Ingestion orchestrator for coordinating chat ingestion from multiple sources.

This orchestrator coordinates the ChatAggregator service to handle
complex ingestion workflows with multiple sources and progress tracking.
"""
from typing import Dict, Callable, Optional, List

from src.core.db import ChatDatabase
from src.services.aggregator import ChatAggregator


class IngestionOrchestrator:
    """
    Orchestrates chat ingestion from multiple sources (Cursor, Claude.ai).

    Coordinates the aggregator service to handle complex workflows involving
    multiple data sources, progress reporting, and statistics aggregation.
    """

    def __init__(self, db: ChatDatabase):
        """
        Initialize orchestrator with database connection.

        Args:
            db: ChatDatabase instance for storing ingested chats
        """
        self.db = db
        self.aggregator = ChatAggregator(db)

    def ingest(
        self,
        source: str = 'cursor',
        incremental: bool = False,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, int]:
        """
        Ingest chats from specified source(s).

        Args:
            source: Source to ingest from ('cursor', 'claude', or 'all')
            incremental: Only ingest chats updated since last run
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary with ingestion statistics:
                - ingested: Number of chats successfully ingested
                - skipped: Number of chats skipped (already up-to-date)
                - errors: Number of errors encountered
        """
        total_stats = {"ingested": 0, "skipped": 0, "errors": 0}

        # Determine which sources to ingest
        sources_to_ingest = self._resolve_sources(source)

        # Ingest from each source
        for src in sources_to_ingest:
            stats = self._ingest_source(src, incremental, progress_callback)
            self._merge_stats(total_stats, stats)

        return total_stats

    def _resolve_sources(self, source: str) -> List[str]:
        """
        Resolve source specification to list of sources.

        Args:
            source: Source specification ('cursor', 'claude', 'chatgpt', or 'all')

        Returns:
            List of source names to ingest from
        """
        if source == 'all':
            return ['cursor', 'claude', 'chatgpt']
        return [source]

    def _ingest_source(
        self,
        source: str,
        incremental: bool,
        progress_callback: Optional[Callable]
    ) -> Dict[str, int]:
        """
        Ingest from a single source.

        Args:
            source: Source name ('cursor', 'claude', or 'chatgpt')
            incremental: Whether to use incremental ingestion
            progress_callback: Optional progress callback

        Returns:
            Statistics dictionary for this source
        """
        if source == 'cursor':
            return self.aggregator.ingest_all(progress_callback, incremental=incremental)
        elif source == 'claude':
            return self.aggregator.ingest_claude(progress_callback, incremental=incremental)
        elif source == 'chatgpt':
            return self.aggregator.ingest_chatgpt(progress_callback, incremental=incremental)
        else:
            return {"ingested": 0, "skipped": 0, "errors": 0}

    def _merge_stats(self, total: Dict[str, int], source: Dict[str, int]):
        """
        Merge source statistics into total statistics.

        Args:
            total: Total statistics dictionary (modified in place)
            source: Source statistics to merge in
        """
        total["ingested"] += source["ingested"]
        total["skipped"] += source["skipped"]
        total["errors"] += source["errors"]
