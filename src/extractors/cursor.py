"""
Cursor data extractor for ELT architecture.

Extracts raw composer conversation data from Cursor SQLite databases
and stores it in RawStorage for later transformation.
"""

import logging
from typing import Any, Dict, Optional

from src.extractors.base import BaseExtractor
from src.readers.global_reader import GlobalComposerReader

logger = logging.getLogger(__name__)


class CursorExtractor(BaseExtractor):
    """
    Extractor for Cursor composer conversations.

    Reads raw composer data from Cursor's global storage database
    (globalStorage/state.vscdb) where composer conversations are stored
    in the cursorDiskKV table with keys like "composerData:{uuid}".

    This extractor performs pure extraction - it reads raw data from
    SQLite databases and stores it without any transformation to Chat models.
    Transformation happens later in the pipeline.

    Attributes
    ----------
    source_name : str
        Always returns 'cursor'
    raw_storage : RawStorage
        Storage instance for raw data
    global_reader : GlobalComposerReader
        Reader for global Cursor database

    Methods
    -------
    extract_all(progress_callback=None)
        Extract all composers from global database
    extract_one(composer_id)
        Extract a single composer by ID
    """

    def __init__(self, raw_storage, global_storage_path=None):
        """
        Initialize Cursor extractor.

        Parameters
        ----------
        raw_storage : RawStorage
            Storage instance for raw data
        global_storage_path : Path, optional
            Path to Cursor globalStorage directory. If None, uses default OS location.
        """
        super().__init__(raw_storage)
        self.global_reader = GlobalComposerReader(global_storage_path)

    @property
    def source_name(self) -> str:
        """
        Source identifier for Cursor data.

        Returns
        -------
        str
            Always returns 'cursor'
        """
        return "cursor"

    def extract_all(self, progress_callback=None) -> Dict[str, int]:
        """
        Extract all composer conversations from Cursor global database.

        Iterates through all composers found in the global database and
        stores their raw data in RawStorage. Tracks statistics for
        extracted, skipped, and error cases.

        Parameters
        ----------
        progress_callback : callable, optional
            Callback(composer_id, total, current) for progress updates.
            Not currently implemented but reserved for future use.

        Returns
        -------
        Dict[str, int]
            Statistics dictionary with keys:
            - 'extracted': number of composers successfully stored
            - 'skipped': number of composers skipped (NULL values, parse errors)
            - 'errors': number of extraction errors encountered
        """
        stats = {"extracted": 0, "skipped": 0, "errors": 0}

        try:
            # Iterate through all composers from global database
            for composer_data in self.global_reader.read_all_composers():
                composer_id = composer_data.get("composer_id")

                if not composer_id:
                    stats["skipped"] += 1
                    logger.debug("Skipping composer with no ID")
                    continue

                try:
                    # Store raw composer data
                    # The raw_data includes the full composer conversation structure
                    raw_data = {
                        "composer_id": composer_id,
                        "key": composer_data.get("key"),
                        "data": composer_data.get("data"),
                    }

                    self._store_raw(composer_id, raw_data)
                    stats["extracted"] += 1

                    logger.debug("Extracted composer %s", composer_id)

                except Exception as e:
                    stats["errors"] += 1
                    logger.error(
                        "Error storing composer %s: %s", composer_id, e, exc_info=True
                    )

        except Exception as e:
            stats["errors"] += 1
            logger.error("Error during extract_all: %s", e, exc_info=True)

        logger.info(
            "Cursor extraction complete: %d extracted, %d skipped, %d errors",
            stats["extracted"],
            stats["skipped"],
            stats["errors"],
        )

        return stats

    def extract_one(self, composer_id: str) -> Optional[Dict[str, Any]]:
        """
        Extract a single composer conversation by ID.

        Reads the composer data from the global database and stores it
        in RawStorage. Returns the raw data dict if found, None otherwise.

        Parameters
        ----------
        composer_id : str
            Composer UUID to extract

        Returns
        -------
        Dict[str, Any] or None
            Raw composer data dict with keys:
            - 'composer_id': the composer UUID
            - 'data': parsed composer conversation data
            Returns None if composer not found or extraction fails.
        """
        try:
            composer_data = self.global_reader.read_composer(composer_id)

            if not composer_data:
                logger.debug("Composer %s not found in global database", composer_id)
                return None

            # Prepare raw data for storage
            raw_data = {
                "composer_id": composer_data.get("composer_id"),
                "data": composer_data.get("data"),
            }

            # Store in raw storage
            self._store_raw(composer_id, raw_data)

            logger.debug("Extracted composer %s", composer_id)

            return raw_data

        except Exception as e:
            logger.error(
                "Error extracting composer %s: %s", composer_id, e, exc_info=True
            )
            return None
