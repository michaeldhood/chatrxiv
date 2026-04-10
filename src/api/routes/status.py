"""
Status API routes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, Depends

from src.api.deps import get_db
from src.api.ingestion_runtime import get_manual_ingest_state
from src.api.schemas import ManualIngestStatus, RuntimeSettingsInfo, StatusResponse, StatusSourceInfo
from src.core.config import (
    get_cursor_global_storage_path,
    get_cursor_workspace_storage_path,
)
from src.core.db import ChatDatabase

router = APIRouter()


def _source_detection(settings: Dict[str, object], source_name: str) -> tuple[bool, bool]:
    if source_name == "cursor":
        workspace_storage = get_cursor_workspace_storage_path()
        global_storage = get_cursor_global_storage_path()
        detected = workspace_storage.exists() or global_storage.exists()
        return detected, detected

    if source_name == "claude-code":
        projects_path = Path(str(settings.get("source.claude_code.projects_path", "")))
        configured = bool(projects_path)
        detected = projects_path.exists()
        return configured, detected

    if source_name == "claude.ai":
        export_path = str(settings.get("source.claude.export_path", "")).strip()
        configured = bool(export_path)
        detected = Path(export_path).expanduser().exists() if configured else False
        return configured, detected

    if source_name == "chatgpt":
        export_path = str(settings.get("source.chatgpt.export_path", "")).strip()
        configured = bool(export_path)
        detected = Path(export_path).expanduser().exists() if configured else False
        return configured, detected

    return False, False


@router.get("/status", response_model=StatusResponse)
def get_status(db: ChatDatabase = Depends(get_db)):
    """Return first-run and source-availability status."""
    from src.api.main import _ingestion_complete

    settings = db.get_all_settings()
    ingestion_states = {row["source"]: row for row in db.list_ingestion_states()}
    source_counts = db.count_chats_by_source()
    manual_state = get_manual_ingest_state()

    sources: List[StatusSourceInfo] = []
    for source_name in ["cursor", "claude.ai", "chatgpt", "claude-code"]:
        state = ingestion_states.get(source_name, {})
        configured, detected = _source_detection(settings, source_name)
        sources.append(
            StatusSourceInfo(
                name=source_name,
                configured=configured,
                detected=detected,
                last_ingestion=state.get("last_run_at"),
                chat_count=source_counts.get(source_name, 0),
            )
        )

    chat_count = db.count_chats()
    return StatusResponse(
        has_data=chat_count > 0,
        chat_count=chat_count,
        sources=sources,
        runtime=RuntimeSettingsInfo(
            watch_enabled=True,
            initial_ingestion_complete=_ingestion_complete.is_set(),
            manual_ingest=ManualIngestStatus(
                running=bool(manual_state.get("running")),
                started_at=manual_state.get("started_at"),
                finished_at=manual_state.get("finished_at"),
                last_error=manual_state.get("last_error"),
                last_stats=manual_state.get("last_result") or {},
            ),
        ),
    )
