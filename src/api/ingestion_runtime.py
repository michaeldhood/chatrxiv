"""
Runtime ingestion status tracking for API-triggered ingestion.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional


_state_lock = threading.Lock()
_manual_ingest_state: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "last_error": None,
    "last_result": None,
    "sources": [],
    "mode": None,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def mark_manual_ingest_started(sources: list[str], mode: str) -> None:
    """Mark a manual ingest run as started."""
    with _state_lock:
        _manual_ingest_state.update(
            {
                "running": True,
                "started_at": _utc_now_iso(),
                "finished_at": None,
                "last_error": None,
                "last_result": None,
                "sources": sources,
                "mode": mode,
            }
        )


def mark_manual_ingest_finished(
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Mark a manual ingest run as finished."""
    with _state_lock:
        _manual_ingest_state.update(
            {
                "running": False,
                "finished_at": _utc_now_iso(),
                "last_error": error,
                "last_result": result,
            }
        )


def get_manual_ingest_state() -> Dict[str, Any]:
    """Return a copy of the current manual ingestion state."""
    with _state_lock:
        return dict(_manual_ingest_state)
