"""
Base transformer interface for ELT architecture.

Transformers read raw data from RawStorage and convert it to
domain models (Chat, Message, Workspace), then store in the domain database.
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Iterator, Optional

from src.core.db import ChatDatabase
from src.core.db.raw_storage import RawStorage
from src.core.models import Chat

logger = logging.getLogger(__name__)


class BaseTransformer(ABC):
    """
    Abstract base class for data transformers.

    Transformers read raw data from RawStorage and convert it to
    normalized domain models for storage in the domain database.

    Attributes
    ----------
    source_name : str
        Source identifier matching extractor's source_name
    raw_storage : RawStorage
        Storage containing raw extracted data
    domain_db : ChatDatabase
        Domain database for transformed data

    Methods
    -------
    transform(raw_data)
        Transform a single raw data dict to domain model
    transform_all(incremental)
        Transform all raw data for this source
    """

    def __init__(self, raw_storage: RawStorage, domain_db: ChatDatabase):
        """
        Initialize transformer.

        Parameters
        ----------
        raw_storage : RawStorage
            Storage containing raw extracted data
        domain_db : ChatDatabase
            Domain database for storing transformed data
        """
        self.raw_storage = raw_storage
        self.domain_db = domain_db

    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        Source identifier matching the extractor.

        Returns
        -------
        str
            Source name: 'cursor', 'claude.ai', 'chatgpt', 'claude-code'
        """

    @abstractmethod
    def transform(self, raw_data: Dict[str, Any]) -> Optional[Chat]:
        """
        Transform raw data to a Chat domain model.

        Parameters
        ----------
        raw_data : Dict
            Raw data from RawStorage (the 'raw_data' field)

        Returns
        -------
        Chat or None
            Transformed Chat model, or None if transformation fails
        """

    def transform_all(
        self,
        incremental: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, int]:
        """
        Transform all raw data for this source.

        Parameters
        ----------
        incremental : bool
            If True, only transform new/updated raw data
        progress_callback : callable, optional
            Callback(source_id, total, current) for progress updates

        Returns
        -------
        Dict[str, int]
            Statistics: {'transformed': count, 'skipped': count, 'errors': count}
        """
        stats = {"transformed": 0, "skipped": 0, "errors": 0}

        # Get raw data from storage
        since = None
        if incremental:
            # Get last transform timestamp from ingestion state
            state = self.domain_db.get_ingestion_state(self.source_name)
            if state and state.get("last_processed_timestamp"):
                try:
                    since = datetime.fromisoformat(state["last_processed_timestamp"])
                except (ValueError, TypeError):
                    pass

        raw_items = list(self.raw_storage.get_all_raw(self.source_name, since=since))
        total = len(raw_items)

        logger.info("Transforming %d raw items for %s", total, self.source_name)

        last_timestamp = None
        for idx, raw_record in enumerate(raw_items, 1):
            source_id = raw_record["source_id"]

            if progress_callback:
                progress_callback(source_id, total, idx)

            try:
                raw_data = raw_record["raw_data"]
                chat = self.transform(raw_data)

                if chat is None:
                    stats["skipped"] += 1
                    continue

                if not chat.messages:
                    stats["skipped"] += 1
                    continue

                self.domain_db.upsert_chat(chat)
                stats["transformed"] += 1

                # Track timestamp for incremental state
                if chat.last_updated_at:
                    if not last_timestamp or chat.last_updated_at > last_timestamp:
                        last_timestamp = chat.last_updated_at

            except Exception as e:
                logger.error("Error transforming %s/%s: %s", self.source_name, source_id, e)
                stats["errors"] += 1

        # Update ingestion state
        if last_timestamp:
            self.domain_db.update_ingestion_state(
                source=self.source_name,
                last_run_at=datetime.utcnow(),
                last_processed_timestamp=last_timestamp.isoformat(),
                stats=stats,
            )

        logger.info(
            "%s transform complete: %d transformed, %d skipped, %d errors",
            self.source_name,
            stats["transformed"],
            stats["skipped"],
            stats["errors"],
        )

        return stats
