"""
Base extractor interface for ELT architecture.

Extractors are responsible for pulling raw data from sources
and storing it in RawStorage. They do NOT transform data.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, Optional

from src.core.db.raw_storage import RawStorage

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """
    Abstract base class for data extractors.

    Extractors read raw data from sources (databases, APIs, files) and
    store it in RawStorage for later transformation.

    Attributes
    ----------
    source_name : str
        Identifier for this source (e.g., 'cursor', 'claude.ai')
    raw_storage : RawStorage
        Storage for raw extracted data

    Methods
    -------
    extract_all()
        Extract all items from the source
    extract_one(source_id)
        Extract a specific item by ID
    """

    def __init__(self, raw_storage: RawStorage):
        """
        Initialize extractor.

        Parameters
        ----------
        raw_storage : RawStorage
            Storage instance for raw data
        """
        self.raw_storage = raw_storage

    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        Source identifier used in RawStorage.

        Returns
        -------
        str
            Source name: 'cursor', 'claude.ai', 'chatgpt', 'claude-code'
        """

    @abstractmethod
    def extract_all(
        self,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, int]:
        """
        Extract all items from the source and store in RawStorage.

        Parameters
        ----------
        progress_callback : callable, optional
            Callback(source_id, total, current) for progress updates

        Returns
        -------
        Dict[str, int]
            Statistics: {'extracted': count, 'skipped': count, 'errors': count}
        """

    @abstractmethod
    def extract_one(self, source_id: str) -> Optional[Dict[str, Any]]:
        """
        Extract a single item by its source ID.

        Parameters
        ----------
        source_id : str
            ID of the item to extract (composer_id, conversation uuid, etc.)

        Returns
        -------
        Dict or None
            Raw data dict if found, None otherwise
        """

    def _store_raw(self, source_id: str, raw_data: Dict[str, Any]) -> int:
        """
        Helper to store raw data in RawStorage.

        Parameters
        ----------
        source_id : str
            ID of the item
        raw_data : Dict
            Raw data to store

        Returns
        -------
        int
            Row ID of stored record
        """
        return self.raw_storage.store_raw(
            source=self.source_name,
            source_id=source_id,
            raw_data=raw_data,
        )
