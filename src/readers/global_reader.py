"""
Reader for global Cursor state database.

Extracts full composer conversations from globalStorage/state.vscdb
cursorDiskKV table where keys are TEXT in format "composerData:{uuid}".
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, List

from src.core.config import get_cursor_global_storage_path

logger = logging.getLogger(__name__)


class GlobalComposerReader:
    """
    Reads full composer conversations from global Cursor database.

    The global database stores all composer data in cursorDiskKV table
    with TEXT keys in format "composerData:{uuid}" (indexed for fast lookups).
    """

    def __init__(self, global_storage_path: Optional[Path] = None):
        """
        Initialize reader.

        Parameters
        ----
        global_storage_path : Path, optional
            Path to globalStorage directory. If None, uses default OS location.
        """
        if global_storage_path is None:
            global_storage_path = get_cursor_global_storage_path()
        self.global_storage_path = global_storage_path
        self.db_path = global_storage_path / "state.vscdb"

    def _extract_composer_id_from_key(self, key: str) -> Optional[str]:
        """
        Extract composer UUID from decoded key.

        Parameters
        ----
        key : str
            Decoded key string (format: "composerData:{uuid}")

        Returns
        ----
        str
            Composer UUID, or None if not found
        """
        if key and key.startswith("composerData:"):
            return key[len("composerData:") :]
        return None

    def read_all_composers(self) -> Iterator[Dict[str, Any]]:
        """
        Read all composer conversations from global database.

        Yields
        ----
        Dict[str, Any]
            Composer data with decoded key and parsed conversation
        """
        if not self.db_path.exists():
            logger.warning("Global database does not exist: %s", self.db_path)
            return

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Check if cursorDiskKV table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='cursorDiskKV'"
            )
            if not cursor.fetchone():
                logger.warning("cursorDiskKV table not found in global database")
                conn.close()
                return

            # Search for keys that start with "composerData:"
            # Use range query with index: key >= 'composerData:' AND key < 'composerData;'
            # The ';' character (ASCII 59) is one after ':' (ASCII 58), capturing all composerData:* keys
            cursor.execute(
                "SELECT key, value FROM cursorDiskKV WHERE key >= ? AND key < ?",
                ("composerData:", "composerData;"),
            )

            count = 0
            for row in cursor.fetchall():
                key_str = row[0]
                value_data = row[1]

                # Extract composer ID from key
                composer_id = self._extract_composer_id_from_key(key_str)
                if not composer_id:
                    continue

                # Cursor occasionally stores NULL/empty payloads; skip safely.
                # This is common (deleted chats leave keys with NULL values).
                if value_data is None:
                    logger.debug(
                        "Skipping composer %s because value is NULL", composer_id
                    )
                    continue

                # Parse value (should be JSON)
                try:
                    if isinstance(value_data, bytes):
                        composer_data = json.loads(value_data.decode("utf-8"))
                    else:
                        composer_data = json.loads(value_data)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.warning(
                        "Failed to parse composer data for %s: %s", composer_id, e
                    )
                    continue

                yield {
                    "composer_id": composer_id,
                    "key": key_str,
                    "data": composer_data,
                }
                count += 1

            conn.close()
            logger.info("Read %d composers from global database", count)

        except sqlite3.Error as e:
            logger.error("Error reading global database: %s", e)

    def read_composer(self, composer_id: str) -> Optional[Dict[str, Any]]:
        """
        Read a specific composer by ID.

        Parameters
        ----
        composer_id : str
            Composer UUID

        Returns
        ----
        Dict[str, Any]
            Composer data, or None if not found
        """
        if not self.db_path.exists():
            return None

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Search for exact key match (uses index)
            key = f"composerData:{composer_id}"
            cursor.execute(
                "SELECT key, value FROM cursorDiskKV WHERE key = ?", (key,)
            )
            row = cursor.fetchone()

            if not row:
                conn.close()
                return None

            # Parse value
            value_data = row[1]
            if value_data is None:
                logger.warning(
                    "Composer %s has NULL value in cursorDiskKV", composer_id
                )
                conn.close()
                return None
            try:
                if isinstance(value_data, bytes):
                    composer_data = json.loads(value_data.decode("utf-8"))
                else:
                    composer_data = json.loads(value_data)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning("Failed to parse composer data: %s", e)
                conn.close()
                return None

            conn.close()

            return {
                "composer_id": composer_id,
                "data": composer_data,
            }

        except sqlite3.Error as e:
            logger.error("Error reading composer %s: %s", composer_id, e)
            return None

    def read_bubble(self, composer_id: str, bubble_id: str) -> Optional[Dict[str, Any]]:
        """
        Read a specific bubble's content by composer and bubble ID.

        Bubble content is stored in separate keys: bubbleId:{composerId}:{bubbleId}

        Parameters
        ----
        composer_id : str
            Composer UUID
        bubble_id : str
            Bubble UUID

        Returns
        ----
        Dict[str, Any]
            Bubble data including text/richText, or None if not found
        """
        if not self.db_path.exists():
            return None

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            key = f"bubbleId:{composer_id}:{bubble_id}"
            cursor.execute(
                "SELECT value FROM cursorDiskKV WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            conn.close()

            if not row or row[0] is None:
                return None

            value_data = row[0]
            if isinstance(value_data, bytes):
                return json.loads(value_data.decode("utf-8"))
            return json.loads(value_data)

        except (sqlite3.Error, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.debug("Error reading bubble %s:%s: %s", composer_id, bubble_id, e)
            return None

    def read_bubbles_batch(self, composer_id: str, bubble_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch multiple bubbles for a composer in a single query.
        
        More efficient than calling read_bubble() multiple times when processing
        conversations with fullConversationHeadersOnly format.
        
        Parameters
        ----
        composer_id : str
            Composer UUID
        bubble_ids : List[str]
            List of bubble UUIDs to fetch
            
        Returns
        ----
        Dict[str, Dict[str, Any]]
            Mapping of bubble_id -> bubble data (only includes found bubbles)
        """
        if not self.db_path.exists() or not bubble_ids:
            return {}
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Build keys and query with IN clause
            keys = [f"bubbleId:{composer_id}:{bubble_id}" for bubble_id in bubble_ids]
            placeholders = ','.join('?' * len(keys))
            
            cursor.execute(
                f"SELECT key, value FROM cursorDiskKV WHERE key IN ({placeholders})",
                keys
            )
            
            bubbles = {}
            for row in cursor.fetchall():
                key_str = row[0]
                value_data = row[1]
                
                if value_data is None:
                    continue
                
                # Extract bubble_id from key (format: bubbleId:{composer_id}:{bubble_id})
                # Key format: "bubbleId:{composer_id}:{bubble_id}"
                parts = key_str.split(':', 2)
                if len(parts) == 3 and parts[0] == "bubbleId":
                    bubble_id = parts[2]
                    try:
                        if isinstance(value_data, bytes):
                            bubble_data = json.loads(value_data.decode("utf-8"))
                        else:
                            bubble_data = json.loads(value_data)
                        bubbles[bubble_id] = bubble_data
                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        logger.debug("Failed to parse bubble %s:%s: %s", composer_id, bubble_id, e)
            
            conn.close()
            return bubbles
            
        except sqlite3.Error as e:
            logger.debug("Error reading bubbles batch for %s: %s", composer_id, e)
            return {}
