import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_db
from src.api.main import app
from src.core.db import ChatDatabase
from src.core.models import Chat, ChatMode, CursorActivity, Message, MessageRole, Workspace


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test-chats.db"


@pytest.fixture
def temp_db(temp_db_path: Path) -> Iterator[ChatDatabase]:
    db = ChatDatabase(str(temp_db_path))
    yield db
    db.close()


@pytest.fixture
def seeded_db(temp_db: ChatDatabase) -> ChatDatabase:
    now = datetime(2026, 4, 10, 12, 0, 0)

    workspace = Workspace(
        workspace_hash="ws-seeded-001",
        folder_uri="file:///workspace/demo",
        resolved_path="/workspace/demo",
        first_seen_at=now - timedelta(days=10),
        last_seen_at=now,
    )
    workspace_id = temp_db.upsert_workspace(workspace)

    chat_one = Chat(
        cursor_composer_id="composer-seeded-001",
        workspace_id=workspace_id,
        title="Python search chat",
        mode=ChatMode.CHAT,
        created_at=now - timedelta(days=2),
        last_updated_at=now - timedelta(days=1),
        source="cursor",
        messages=[
            Message(
                role=MessageRole.USER,
                text="How do I search in python?",
                created_at=now - timedelta(days=2),
            ),
            Message(
                role=MessageRole.ASSISTANT,
                text="Use ripgrep or Python filtering for fast search results.",
                created_at=now - timedelta(days=2),
            ),
        ],
        relevant_files=["/workspace/demo/app.py"],
    )
    chat_one_id = temp_db.upsert_chat(chat_one)
    temp_db.add_tags(chat_one_id, ["tech/python", "topic/search"])

    chat_two = Chat(
        cursor_composer_id="composer-seeded-002",
        workspace_id=workspace_id,
        title="Database activity chat",
        mode=ChatMode.AGENT,
        created_at=now - timedelta(days=1),
        last_updated_at=now,
        source="claude-code",
        messages=[
            Message(
                role=MessageRole.USER,
                text="Review the SQLite activity endpoint",
                created_at=now - timedelta(days=1),
            ),
            Message(
                role=MessageRole.ASSISTANT,
                text="The endpoint returns aggregated cursor activity data.",
                created_at=now - timedelta(days=1),
            ),
        ],
        relevant_files=["/workspace/demo/activity.py"],
    )
    chat_two_id = temp_db.upsert_chat(chat_two)
    temp_db.add_tags(chat_two_id, ["activity/cost", "topic/database"])

    empty_chat = Chat(
        cursor_composer_id="composer-seeded-003",
        workspace_id=workspace_id,
        title="Legacy Empty Chat",
        mode=ChatMode.CHAT,
        created_at=now - timedelta(days=3),
        last_updated_at=now - timedelta(days=3),
        source="legacy",
        messages=[],
        relevant_files=[],
    )
    temp_db.upsert_chat(empty_chat)

    plan_id = temp_db.upsert_plan(
        plan_id="plan-seeded-001",
        name="Launch plan",
        file_path="/workspace/demo/launch.plan.md",
        created_at=now - timedelta(days=2),
        last_updated_at=now - timedelta(days=1),
    )
    temp_db.link_chat_to_plan(chat_one_id, plan_id, "created")

    temp_db.upsert_activity(
        CursorActivity(
            date=datetime(2026, 4, 1, 9, 0, 0),
            kind="Included",
            model="claude-3-5-sonnet",
            input_tokens_with_cache=120,
            input_tokens_no_cache=80,
            cache_read_tokens=30,
            output_tokens=45,
            total_tokens=275,
            cost=1.23,
        )
    )
    temp_db.upsert_activity(
        CursorActivity(
            date=datetime(2026, 4, 2, 9, 0, 0),
            kind="Included",
            model="claude-3-haiku",
            input_tokens_with_cache=150,
            input_tokens_no_cache=110,
            cache_read_tokens=40,
            output_tokens=65,
            total_tokens=365,
            cost=0.77,
        )
    )

    temp_db.update_ingestion_state(
        source="cursor",
        last_run_at=now - timedelta(hours=1),
        last_processed_timestamp=(now - timedelta(hours=1)).isoformat(),
        last_composer_id="composer-seeded-002",
        stats={"ingested": 3, "skipped": 0, "errors": 0},
    )

    return temp_db


@pytest.fixture
def api_client(seeded_db: ChatDatabase) -> Iterator[TestClient]:
    os.environ["CHATRXIV_WATCH"] = "false"

    def override_get_db():
        yield seeded_db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def client(api_client: TestClient) -> TestClient:
    """Backward-compatible alias for route tests expecting `client`."""
    return api_client

