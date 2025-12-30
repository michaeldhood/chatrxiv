"""
Loader for cursor activity data.

Handles importing activity data from exported files (CSV, JSON).
"""
import json
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.core.models import CursorActivity
from src.core.db import ChatDatabase

logger = logging.getLogger(__name__)


class ActivityLoader:
    """
    Loads cursor activity data from exported files.
    
    Supports CSV and JSON formats.
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
    
    def load_from_json(self, file_path: str) -> int:
        """
        Load activity data from a JSON file.
        
        Expected JSON format:
        [
            {
                "timestamp": "2024-01-01T12:00:00",
                "activity_type": "chat",
                "model": "claude-3-5-sonnet-20241022",
                "workspace_hash": "...",
                "composer_id": "...",
                "tokens_input": 1000,
                "tokens_output": 500,
                "cost": 0.005,
                "metadata": {...}
            },
            ...
        ]
        
        Parameters
        ----
        file_path : str
            Path to JSON file
            
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
            with open(file_path_obj, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list):
                logger.error("JSON file must contain an array of activity objects")
                return 0
            
            loaded_count = 0
            for item in data:
                try:
                    activity = self._parse_activity_item(item)
                    if activity:
                        self.db.upsert_activity(activity)
                        loaded_count += 1
                except Exception as e:
                    logger.warning("Failed to parse activity item: %s", e)
                    continue
            
            logger.info("Loaded %d activities from %s", loaded_count, file_path)
            return loaded_count
            
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON file %s: %s", file_path, e)
            return 0
        except Exception as e:
            logger.error("Error loading JSON file %s: %s", file_path, e)
            return 0
    
    def load_from_csv(self, file_path: str) -> int:
        """
        Load activity data from a CSV file.
        
        Expected CSV format:
        timestamp,activity_type,model,workspace_hash,composer_id,tokens_input,tokens_output,cost,metadata
        
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
            with open(file_path_obj, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    try:
                        activity = self._parse_csv_row(row)
                        if activity:
                            self.db.upsert_activity(activity)
                            loaded_count += 1
                    except Exception as e:
                        logger.warning("Failed to parse CSV row: %s", e)
                        continue
            
            logger.info("Loaded %d activities from %s", loaded_count, file_path)
            return loaded_count
            
        except Exception as e:
            logger.error("Error loading CSV file %s: %s", file_path, e)
            return 0
    
    def _parse_activity_item(self, item: Dict[str, Any]) -> Optional[CursorActivity]:
        """
        Parse a single activity item from JSON.
        
        Parameters
        ----
        item : Dict[str, Any]
            Activity data dictionary
            
        Returns
        ----
        CursorActivity, optional
            Parsed activity or None if invalid
        """
        try:
            # Parse timestamp
            timestamp_str = item.get("timestamp")
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except ValueError:
                    logger.warning("Invalid timestamp format: %s", timestamp_str)
                    timestamp = None
            else:
                timestamp = None
            
            # Parse metadata if it's a string
            metadata = item.get("metadata")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    metadata = None
            
            activity = CursorActivity(
                timestamp=timestamp,
                activity_type=item.get("activity_type", "unknown"),
                model=item.get("model"),
                workspace_hash=item.get("workspace_hash"),
                composer_id=item.get("composer_id"),
                chat_id=item.get("chat_id"),
                tokens_input=item.get("tokens_input"),
                tokens_output=item.get("tokens_output"),
                cost=item.get("cost"),
                metadata=metadata,
            )
            
            return activity
            
        except Exception as e:
            logger.warning("Error parsing activity item: %s", e)
            return None
    
    def _parse_csv_row(self, row: Dict[str, str]) -> Optional[CursorActivity]:
        """
        Parse a CSV row into a CursorActivity.
        
        Parameters
        ----
        row : Dict[str, str]
            CSV row as dictionary
            
        Returns
        ----
        CursorActivity, optional
            Parsed activity or None if invalid
        """
        try:
            # Parse timestamp
            timestamp_str = row.get("timestamp", "")
            timestamp = None
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except ValueError:
                    pass
            
            # Parse numeric fields
            tokens_input = None
            if row.get("tokens_input"):
                try:
                    tokens_input = int(row["tokens_input"])
                except ValueError:
                    pass
            
            tokens_output = None
            if row.get("tokens_output"):
                try:
                    tokens_output = int(row["tokens_output"])
                except ValueError:
                    pass
            
            cost = None
            if row.get("cost"):
                try:
                    cost = float(row["cost"])
                except ValueError:
                    pass
            
            chat_id = None
            if row.get("chat_id"):
                try:
                    chat_id = int(row["chat_id"])
                except ValueError:
                    pass
            
            # Parse metadata
            metadata = None
            if row.get("metadata"):
                try:
                    metadata = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    pass
            
            activity = CursorActivity(
                timestamp=timestamp,
                activity_type=row.get("activity_type", "unknown"),
                model=row.get("model") or None,
                workspace_hash=row.get("workspace_hash") or None,
                composer_id=row.get("composer_id") or None,
                chat_id=chat_id,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                cost=cost,
                metadata=metadata,
            )
            
            return activity
            
        except Exception as e:
            logger.warning("Error parsing CSV row: %s", e)
            return None
