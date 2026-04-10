"""
Settings repository for application configuration storage.
"""

import json
from typing import Any, Dict, Optional

from .base import BaseRepository


class SettingsRepository(BaseRepository):
    """
    Repository for persisted application settings.

    Stores arbitrary key/value settings in a small key-value table.
    Values are serialized as JSON for flexibility.
    """

    def get(self, key: str) -> Optional[Any]:
        """Get a setting value by key."""
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT value
            FROM app_settings
            WHERE key = ?
            """,
            (key,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        value = row[0]
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    def set(self, key: str, value: Any) -> None:
        """Set a setting value by key."""
        cursor = self.cursor()
        cursor.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, json.dumps(value)),
        )
        self.commit()

    def get_all(self) -> Dict[str, Any]:
        """Get all settings as a dictionary."""
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT key, value
            FROM app_settings
            ORDER BY key
            """
        )

        settings: Dict[str, Any] = {}
        for row in cursor.fetchall():
            try:
                settings[row[0]] = json.loads(row[1])
            except (json.JSONDecodeError, TypeError):
                settings[row[0]] = row[1]
        return settings
"""
Settings repository for application configuration storage.
"""

import json
from typing import Any, Dict, Optional

from .base import BaseRepository


class SettingsRepository(BaseRepository):
    """
    Repository for persisted application settings.

    Stores arbitrary key/value settings in a small key-value table.
    Values are serialized as JSON for flexibility.
    """

    def get(self, key: str) -> Optional[Any]:
        """Get a setting value by key."""
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT value
            FROM app_settings
            WHERE key = ?
            """,
            (key,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        value = row[0]
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    def set(self, key: str, value: Any) -> None:
        """Set a setting value by key."""
        cursor = self.cursor()
        cursor.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, json.dumps(value)),
        )
        self.commit()

    def get_all(self) -> Dict[str, Any]:
        """Get all settings as a dictionary."""
        cursor = self.cursor()
        cursor.execute(
            """
            SELECT key, value
            FROM app_settings
            ORDER BY key
            """
        )

        settings: Dict[str, Any] = {}
        for row in cursor.fetchall():
            try:
                settings[row[0]] = json.loads(row[1])
            except (json.JSONDecodeError, TypeError):
                settings[row[0]] = row[1]
        return settings
