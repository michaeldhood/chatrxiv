"""
Settings and ingestion API routes.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from src.api.deps import get_db
from src.api.ingestion_runtime import (
    get_manual_ingest_state,
    mark_manual_ingest_finished,
    mark_manual_ingest_started,
)
from src.api.schemas import (
    IngestRequest,
    IngestResponse,
    IngestionStateInfo,
    SettingsResponse,
)
from src.core.config import (
    get_default_chatgpt_export_path,
    get_claude_code_projects_path,
    get_default_claude_export_path,
    get_cursor_workspace_storage_path,
    get_default_raw_db_path,
)
from src.core.db import ChatDatabase
from src.services.aggregator import ChatAggregator

router = APIRouter()
logger = logging.getLogger(__name__)


def _safe_file_size(path: str) -> Optional[int]:
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _build_default_settings() -> Dict[str, str]:
    return {
        "source.cursor.workspace_storage_path": str(get_cursor_workspace_storage_path()),
        "source.claude_code.projects_path": str(get_claude_code_projects_path()),
        "source.claude.export_path": str(get_default_claude_export_path()),
        "source.chatgpt.export_path": str(get_default_chatgpt_export_path()),
    }


def _ensure_default_settings(db: ChatDatabase) -> Dict[str, Any]:
    defaults = _build_default_settings()
    existing = db.get_all_settings()
    for key, value in defaults.items():
        if key not in existing:
            db.set_setting(key, value)
    merged = defaults.copy()
    merged.update(db.get_all_settings())
    return merged


def _list_ingestion_sources(db: ChatDatabase) -> List[IngestionStateInfo]:
    sources: List[IngestionStateInfo] = []
    states = {row["source"]: row for row in db.list_ingestion_states()}
    for source_name in ["cursor", "claude.ai", "chatgpt", "claude-code"]:
        row = states.get(source_name)
        sources.append(
            IngestionStateInfo(
                source=source_name,
                last_run_at=row.get("last_run_at") if row else None,
                last_processed_timestamp=row.get("last_processed_timestamp") if row else None,
                last_composer_id=row.get("last_composer_id") if row else None,
                stats_ingested=row.get("stats_ingested", 0) if row else 0,
                stats_skipped=row.get("stats_skipped", 0) if row else 0,
                stats_errors=row.get("stats_errors", 0) if row else 0,
            )
        )
    return sources


@router.get("/settings", response_model=SettingsResponse)
def get_settings(db: ChatDatabase = Depends(get_db)):
    """Return persisted settings plus runtime ingestion information."""
    from src.api.main import _ingestion_complete

    settings = _ensure_default_settings(db)
    chats_db_path = db.conn.db_path
    raw_db_path = str(get_default_raw_db_path())
    manual_state = get_manual_ingest_state()

    return SettingsResponse(
        settings=[
            {"key": key, "value": value}
            for key, value in sorted(settings.items())
        ],
        database={
            "chats_db_path": chats_db_path,
            "chats_db_size_bytes": _safe_file_size(chats_db_path),
            "raw_db_path": raw_db_path,
            "raw_db_size_bytes": _safe_file_size(raw_db_path),
        },
        ingestion=_list_ingestion_sources(db),
        runtime={
            "watch_enabled": os.getenv("CHATRXIV_WATCH", "true").lower() == "true",
            "initial_ingestion_complete": _ingestion_complete.is_set(),
            "manual_ingest": {
                "running": bool(manual_state.get("running")),
                "started_at": manual_state.get("started_at"),
                "finished_at": manual_state.get("finished_at"),
                "last_error": manual_state.get("last_error"),
                "last_stats": manual_state.get("last_result") or {},
            },
        },
    )


def _run_manual_ingestion(
    db_path: str,
    sources: List[str],
    incremental: bool,
) -> None:
    db = ChatDatabase(db_path)
    aggregator = ChatAggregator(db)
    mode = "incremental" if incremental else "full"
    mark_manual_ingest_started(sources, mode)

    try:
        result: Dict[str, object] = {}
        for source in sources:
            if source == "cursor":
                result[source] = aggregator.ingest_all(incremental=incremental)
            elif source == "claude-code":
                result[source] = aggregator.ingest_claude_code(incremental=incremental)
            elif source == "claude.ai":
                result[source] = aggregator.ingest_claude(incremental=incremental)
            elif source == "chatgpt":
                result[source] = aggregator.ingest_chatgpt(incremental=incremental)
        mark_manual_ingest_finished(result=result)
    except Exception as exc:  # pragma: no cover - exercised via route tests later
        logger.exception("Manual ingestion failed")
        mark_manual_ingest_finished(error=str(exc))
    finally:
        db.close()


@router.post("/ingest", response_model=IngestResponse)
def trigger_ingest(
    body: IngestRequest,
    db: ChatDatabase = Depends(get_db),
):
    """Trigger ingestion in a background thread."""
    sources = body.sources or ["cursor", "claude-code"]
    thread = threading.Thread(
        target=_run_manual_ingestion,
        args=(db.conn.db_path, sources, body.mode == "incremental"),
        daemon=True,
    )
    thread.start()
    return IngestResponse(
        accepted=True,
        message="Ingestion started in background",
        mode=body.mode,
        sources=sources,
    )
