"""
Loader for cursor activity data.

Handles importing activity data from exported CSV files matching Cursor's export format.
"""
import csv
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from src.core.models import CursorActivity
from src.core.db import ChatDatabase

logger = logging.getLogger(__name__)


class ActivityLoader:
    """
    Loads cursor activity data from exported CSV files.

    Supports the Cursor export format with columns:
    Date, Kind, Model, Max Mode, Input (w/ Cache Write), Input (w/o Cache Write),
    Cache Read, Output Tokens, Total Tokens, Cost
    """

    def __init__(self, db: ChatDatabase):
        """
        Initialize activity loader.

        Parameters
        ----
        db : ChatDatabase
            Database instance
        """
        self.db = db

    def load_from_csv(self, file_path: str) -> int:
        """
        Load activity data from a CSV file.

        Expected CSV format (from Cursor export):
        Date,Kind,Model,Max Mode,Input (w/ Cache Write),Input (w/o Cache Write),
        Cache Read,Output Tokens,Total Tokens,Cost

        Parameters
        ----
        file_path : str
            Path to CSV file

        Returns
        ----
        int
            Number of activities loaded
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            logger.error("File not found: %s", file_path)
            return 0

        try:
            loaded_count = 0
            skipped_count = 0
            with open(file_path_obj, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                    try:
                        activity = self._parse_csv_row(row)
                        if activity:
                            activity_id = self.db.upsert_activity(activity)
                            if activity_id:
                                loaded_count += 1
                            else:
                                skipped_count += 1  # Duplicate
                        else:
                            skipped_count += 1
                    except Exception as e:
                        logger.warning(
                            "Failed to parse CSV row %d: %s", row_num, e
                        )
                        continue

            logger.info(
                "Loaded %d activities from %s (%d skipped)",
                loaded_count,
                file_path,
                skipped_count,
            )
            return loaded_count

        except Exception as e:
            logger.error("Error loading CSV file %s: %s", file_path, e)
            return 0

    def _parse_csv_row(self, row: dict) -> Optional[CursorActivity]:
        """
        Parse a CSV row into a CursorActivity.

        Parameters
        ----
        row : dict
            CSV row as dictionary

        Returns
        ----
        CursorActivity, optional
            Parsed activity or None if invalid
        """
        try:
            # Parse date
            date_str = row.get("Date", "").strip()
            date = None
            if date_str:
                try:
                    # Handle ISO format with Z suffix
                    date_str = date_str.replace("Z", "+00:00")
                    date = datetime.fromisoformat(date_str)
                except ValueError:
                    logger.warning("Invalid date format: %s", date_str)
                    return None

            # Parse max_mode (Yes/No -> bool)
            max_mode_str = row.get("Max Mode", "").strip().lower()
            max_mode = None
            if max_mode_str:
                max_mode = max_mode_str in ("yes", "true", "1")

            # Parse numeric fields
            def parse_int(value: str) -> Optional[int]:
                if not value or not value.strip():
                    return None
                try:
                    return int(float(value.strip()))
                except (ValueError, TypeError):
                    return None

            def parse_float(value: str) -> Optional[float]:
                if not value or not value.strip():
                    return None
                try:
                    return float(value.strip())
                except (ValueError, TypeError):
                    return None

            activity = CursorActivity(
                date=date,
                kind=row.get("Kind", "").strip() or "unknown",
                model=row.get("Model", "").strip() or None,
                max_mode=max_mode,
                input_tokens_with_cache=parse_int(
                    row.get("Input (w/ Cache Write)", "")
                ),
                input_tokens_no_cache=parse_int(
                    row.get("Input (w/o Cache Write)", "")
                ),
                cache_read_tokens=parse_int(row.get("Cache Read", "")),
                output_tokens=parse_int(row.get("Output Tokens", "")),
                total_tokens=parse_int(row.get("Total Tokens", "")),
                cost=parse_float(row.get("Cost", "")),
            )

            return activity

        except Exception as e:
            logger.warning("Error parsing CSV row: %s", e)
            return None
