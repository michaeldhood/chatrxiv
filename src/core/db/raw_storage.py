"""
Raw data storage for ELT architecture.

Provides a RawStorage class that manages a separate SQLite database (raw.db)
for storing full raw JSON extracts from all sources (Cursor, Claude.ai,
ChatGPT, Claude Code). This enables Extract-Load-Transform architecture
where raw data is preserved before transformation.

Design Patterns
---------------
Repository pattern with deduplication via content checksums.

External Dependencies
---------------------
- hashlib: MD5 checksums for deduplication
- sqlite3: Database storage

Technical Decisions
-------------------
Separate database file (raw.db) keeps raw archives isolated from the
transformed chat database (chats.db), allowing independent backup and
maintenance strategies.
"""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from src.core.config import get_default_db_path

logger = logging.getLogger(__name__)


# Schema definition
RAW_STORAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_extracts (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    checksum TEXT,
    UNIQUE(source, source_id, checksum)
);

CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_extracts(source);
CREATE INDEX IF NOT EXISTS idx_raw_source_id ON raw_extracts(source, source_id);
CREATE INDEX IF NOT EXISTS idx_raw_extracted_at ON raw_extracts(extracted_at);
"""


class RawStorage:
    """
    Archive of raw extracted data from all sources.

    Manages a separate SQLite database for storing full raw JSON extracts
    from Cursor, Claude.ai, ChatGPT, and Claude Code. Uses MD5 checksums
    for deduplication to avoid storing identical data multiple times.

    Attributes
    ----------
    db_path : Path
        Path to the raw.db database file
    _conn : sqlite3.Connection
        SQLite connection with WAL mode enabled

    Methods
    -------
    store_raw(source, source_id, raw_data, extracted_at)
        Store raw extraction data with deduplication
    get_raw(source, source_id)
        Get latest raw data for a source item
    get_all_raw(source, since)
        Stream all raw data for a source
    count(source)
        Count raw extracts, optionally filtered by source
    get_sources()
        Get list of distinct sources in storage

    Example
    -------
    >>> storage = RawStorage()
    >>> row_id = storage.store_raw("cursor", "composer-123", {"bubbles": [...]})
    >>> data = storage.get_raw("cursor", "composer-123")
    >>> print(data["source_id"])
    'composer-123'
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize raw storage.

        Parameters
        ----------
        db_path : Path, optional
            Path to raw.db file. If None, uses default location
            (same directory as chats.db but named raw.db)
        """
        if db_path is None:
            db_path = get_default_db_path().parent / "raw.db"

        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._ensure_schema()

    def _connect(self) -> None:
        """Establish database connection with WAL mode."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # Enable WAL mode for concurrent read/write access
        cursor = self._conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.fetchone()  # Consume the result

        logger.debug("Raw storage connection established: %s", self.db_path)

    def _ensure_schema(self) -> None:
        """Create schema if it doesn't exist."""
        cursor = self._conn.cursor()
        cursor.executescript(RAW_STORAGE_SCHEMA)
        self._conn.commit()
        logger.debug("Raw storage schema ensured")

    @property
    def connection(self) -> sqlite3.Connection:
        """Get the underlying SQLite connection."""
        if self._conn is None:
            self._connect()
        return self._conn

    def _compute_checksum(self, data: Dict[str, Any]) -> str:
        """
        Compute MD5 checksum of JSON data for deduplication.

        Parameters
        ----------
        data : Dict
            Data to compute checksum for

        Returns
        -------
        str
            MD5 hex digest of the JSON-serialized data
        """
        # Sort keys for consistent serialization
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(json_str.encode("utf-8")).hexdigest()

    def store_raw(
        self,
        source: str,
        source_id: str,
        raw_data: Dict[str, Any],
        extracted_at: Optional[datetime] = None,
    ) -> int:
        """
        Store raw extraction data.

        Parameters
        ----------
        source : str
            Source identifier: 'cursor', 'claude.ai', 'chatgpt', 'claude-code'
        source_id : str
            Original ID from source (composer_id, conversation uuid, session_id)
        raw_data : Dict
            Full raw JSON data from source
        extracted_at : datetime, optional
            Extraction timestamp. Defaults to now.

        Returns
        -------
        int
            Row ID of inserted/existing record

        Notes
        -----
        Uses checksum for deduplication - if identical data already exists,
        returns existing row ID without inserting duplicate.
        """
        if extracted_at is None:
            extracted_at = datetime.utcnow()

        checksum = self._compute_checksum(raw_data)
        raw_json = json.dumps(raw_data, default=str)
        extracted_at_str = extracted_at.isoformat()

        cursor = self.connection.cursor()

        # Check for existing record with same checksum (deduplication)
        cursor.execute(
            """
            SELECT id FROM raw_extracts
            WHERE source = ? AND source_id = ? AND checksum = ?
            """,
            (source, source_id, checksum),
        )
        existing = cursor.fetchone()

        if existing:
            logger.debug(
                "Duplicate raw data for %s/%s (checksum: %s), returning existing id=%d",
                source,
                source_id,
                checksum[:8],
                existing["id"],
            )
            return existing["id"]

        # Insert new record
        cursor.execute(
            """
            INSERT INTO raw_extracts (source, source_id, extracted_at, raw_json, checksum)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source, source_id, extracted_at_str, raw_json, checksum),
        )
        self.connection.commit()

        row_id = cursor.lastrowid
        logger.debug(
            "Stored raw data for %s/%s (checksum: %s, id=%d)",
            source,
            source_id,
            checksum[:8],
            row_id,
        )
        return row_id

    def get_raw(self, source: str, source_id: str) -> Optional[Dict[str, Any]]:
        """
        Get latest raw data for a source item.

        Parameters
        ----------
        source : str
            Source identifier
        source_id : str
            Original ID from source

        Returns
        -------
        Dict or None
            Latest raw data dict with keys: id, source, source_id,
            extracted_at, raw_data (parsed JSON), checksum
        """
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT id, source, source_id, extracted_at, raw_json, checksum
            FROM raw_extracts
            WHERE source = ? AND source_id = ?
            ORDER BY extracted_at DESC
            LIMIT 1
            """,
            (source, source_id),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "id": row["id"],
            "source": row["source"],
            "source_id": row["source_id"],
            "extracted_at": row["extracted_at"],
            "raw_data": json.loads(row["raw_json"]),
            "checksum": row["checksum"],
        }

    def get_all_raw(
        self,
        source: str,
        since: Optional[datetime] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Stream all raw data for a source.

        Parameters
        ----------
        source : str
            Source identifier to filter by
        since : datetime, optional
            Only return extracts after this timestamp

        Yields
        ------
        Dict
            Raw data records with parsed raw_data JSON
        """
        cursor = self.connection.cursor()

        if since is not None:
            since_str = since.isoformat()
            cursor.execute(
                """
                SELECT id, source, source_id, extracted_at, raw_json, checksum
                FROM raw_extracts
                WHERE source = ? AND extracted_at > ?
                ORDER BY extracted_at ASC
                """,
                (source, since_str),
            )
        else:
            cursor.execute(
                """
                SELECT id, source, source_id, extracted_at, raw_json, checksum
                FROM raw_extracts
                WHERE source = ?
                ORDER BY extracted_at ASC
                """,
                (source,),
            )

        for row in cursor:
            yield {
                "id": row["id"],
                "source": row["source"],
                "source_id": row["source_id"],
                "extracted_at": row["extracted_at"],
                "raw_data": json.loads(row["raw_json"]),
                "checksum": row["checksum"],
            }

    def count(self, source: Optional[str] = None) -> int:
        """
        Count raw extracts, optionally filtered by source.

        Parameters
        ----------
        source : str, optional
            Source identifier to filter by. If None, counts all sources.

        Returns
        -------
        int
            Number of raw extract records
        """
        cursor = self.connection.cursor()

        if source is not None:
            cursor.execute(
                "SELECT COUNT(*) FROM raw_extracts WHERE source = ?",
                (source,),
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM raw_extracts")

        return cursor.fetchone()[0]

    def get_sources(self) -> List[str]:
        """
        Get list of distinct sources in storage.

        Returns
        -------
        List[str]
            List of unique source identifiers
        """
        cursor = self.connection.cursor()
        cursor.execute("SELECT DISTINCT source FROM raw_extracts ORDER BY source")
        return [row["source"] for row in cursor.fetchall()]

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("Raw storage connection closed: %s", self.db_path)

    def __enter__(self) -> "RawStorage":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - close connection."""
        self.close()
