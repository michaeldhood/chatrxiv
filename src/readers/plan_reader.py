"""
Reader for Cursor plan registry.

Extracts plan metadata from globalStorage/state.vscdb ItemTable
where the key is "composer.planRegistry".
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.config import get_cursor_global_storage_path

logger = logging.getLogger(__name__)


class PlanRegistryReader:
    """
    Reads plan registry from global Cursor database.

    The plan registry is stored in ItemTable with key "composer.planRegistry"
    and contains a JSON object mapping plan IDs to plan metadata.
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

    def read_plan_registry(self) -> Dict[str, Dict[str, Any]]:
        """
        Read the plan registry from ItemTable.

        Returns
        ----
        Dict[str, Dict[str, Any]]
            Dictionary mapping plan IDs to plan metadata. Each plan dict contains:
            - id: Plan ID
            - name: Plan name
            - uri: File URI object with fsPath
            - createdBy: Composer ID that created the plan
            - editedBy: List of composer IDs that edited the plan
            - referencedBy: List of composer IDs that referenced the plan
            - builtBy: Dict mapping composer IDs to build data
            - createdAt: Unix timestamp (ms)
            - lastUpdatedAt: Unix timestamp (ms)
        """
        if not self.db_path.exists():
            logger.warning("Global database does not exist: %s", self.db_path)
            return {}

        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Check if ItemTable exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ItemTable'"
            )
            if not cursor.fetchone():
                logger.warning("ItemTable not found in global database")
                conn.close()
                return {}

            # Read plan registry
            cursor.execute(
                "SELECT value FROM ItemTable WHERE key = ?", ("composer.planRegistry",)
            )
            row = cursor.fetchone()
            conn.close()

            if not row:
                logger.debug("Plan registry not found in ItemTable")
                return {}

            # Parse JSON value
            value_data = row[0]
            if isinstance(value_data, bytes):
                # Decode if stored as bytes
                value_data = value_data.decode("utf-8")

            plan_registry = json.loads(value_data)
            logger.info("Loaded %d plans from registry", len(plan_registry))
            return plan_registry

        except sqlite3.Error as e:
            logger.error("Error reading plan registry: %s", e)
            return {}
        except json.JSONDecodeError as e:
            logger.error("Error parsing plan registry JSON: %s", e)
            return {}

    def get_plan_metadata(self) -> List[Dict[str, Any]]:
        """
        Get normalized plan metadata with composer relationships.

        Returns
        ----
        List[Dict[str, Any]]
            List of plan dictionaries with normalized structure:
            - plan_id: Unique plan identifier
            - name: Plan name
            - file_path: Resolved file system path
            - created_at: ISO timestamp string
            - last_updated_at: ISO timestamp string
            - created_by: Composer ID that created the plan
            - edited_by: List of composer IDs that edited the plan
            - referenced_by: List of composer IDs that referenced the plan
        """
        registry = self.read_plan_registry()
        plans = []

        for plan_id, plan_data in registry.items():
            # Extract file path from URI
            file_path = None
            uri = plan_data.get("uri", {})
            if isinstance(uri, dict):
                file_path = uri.get("fsPath") or uri.get("path")

            # Convert timestamps from milliseconds to datetime objects
            created_at = None
            if plan_data.get("createdAt"):
                try:
                    created_at = datetime.fromtimestamp(
                        plan_data["createdAt"] / 1000
                    )
                except (ValueError, TypeError):
                    pass

            last_updated_at = None
            if plan_data.get("lastUpdatedAt"):
                try:
                    last_updated_at = datetime.fromtimestamp(
                        plan_data["lastUpdatedAt"] / 1000
                    )
                except (ValueError, TypeError):
                    pass

            plans.append(
                {
                    "plan_id": plan_id,
                    "name": plan_data.get("name", ""),
                    "file_path": file_path,
                    "created_at": created_at,
                    "last_updated_at": last_updated_at,
                    "created_by": plan_data.get("createdBy"),
                    "edited_by": plan_data.get("editedBy", []),
                    "referenced_by": plan_data.get("referencedBy", []),
                }
            )

        return plans
