"""
Characterization tests for db.py before refactor.

These tests document current behavior and serve as a safety net during the
refactor to repository pattern. They test major operations, not edge cases.

Purpose:
- Catch catastrophic breakage during refactor
- Document expected behavior
- NOT comprehensive coverage
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta

from src.core.db import ChatDatabase
from src.core.models import (
    Chat,
    Message,
    Workspace,
    CursorActivity,
    ChatMode,
    MessageRole,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = ChatDatabase(path)
    yield db
    db.close()
    os.unlink(path)


@pytest.fixture
def workspace_with_chat(temp_db):
    """Create a workspace with a chat for tests that need pre-existing data."""
    workspace = Workspace(
        workspace_hash="fixture-ws-123",
        folder_uri="file:///test/project",
        resolved_path="/test/project",
    )
    workspace_id = temp_db.upsert_workspace(workspace)

    chat = Chat(
        cursor_composer_id="fixture-chat-123",
        workspace_id=workspace_id,
        title="Fixture Chat",
        mode=ChatMode.CHAT,
        created_at=datetime.now(),
        messages=[
            Message(
                role=MessageRole.USER,
                text="Hello from fixture",
                created_at=datetime.now(),
            ),
            Message(
                role=MessageRole.ASSISTANT,
                text="Fixture response",
                created_at=datetime.now(),
            ),
        ],
    )
    chat_id = temp_db.upsert_chat(chat)

    return {"db": temp_db, "workspace_id": workspace_id, "chat_id": chat_id}


# =============================================================================
# 1. Chat round-trip
# =============================================================================
def test_chat_upsert_and_retrieve(temp_db):
    """Upsert a chat with messages, retrieve it, verify data integrity."""
    # Setup workspace
    workspace = Workspace(workspace_hash="test-ws-001")
    workspace_id = temp_db.upsert_workspace(workspace)

    # Create chat with messages
    now = datetime.now()
    chat = Chat(
        cursor_composer_id="test-chat-001",
        workspace_id=workspace_id,
        title="Test Chat Title",
        mode=ChatMode.AGENT,
        created_at=now,
        model="claude-3-5-sonnet",
        estimated_cost=0.05,
        messages=[
            Message(
                role=MessageRole.USER,
                text="First message",
                created_at=now,
            ),
            Message(
                role=MessageRole.ASSISTANT,
                text="Second message",
                rich_text="**Second** message",
                created_at=now,
            ),
        ],
    )

    chat_id = temp_db.upsert_chat(chat)
    assert chat_id is not None
    assert isinstance(chat_id, int)

    # Retrieve and verify
    retrieved = temp_db.get_chat(chat_id)
    assert retrieved is not None
    assert retrieved["title"] == "Test Chat Title"
    assert retrieved["mode"] == "agent"
    assert retrieved["model"] == "claude-3-5-sonnet"
    assert len(retrieved["messages"]) == 2
    assert retrieved["messages"][0]["text"] == "First message"
    assert retrieved["messages"][1]["rich_text"] == "**Second** message"


# =============================================================================
# 2. Chat with empty messages
# =============================================================================
def test_chat_with_no_messages(temp_db):
    """Edge case: chat with zero messages stores and retrieves correctly."""
    workspace = Workspace(workspace_hash="empty-ws")
    workspace_id = temp_db.upsert_workspace(workspace)

    chat = Chat(
        cursor_composer_id="empty-chat-001",
        workspace_id=workspace_id,
        title="Empty Chat",
        messages=[],
    )

    chat_id = temp_db.upsert_chat(chat)
    retrieved = temp_db.get_chat(chat_id)

    assert retrieved is not None
    assert retrieved["title"] == "Empty Chat"
    assert len(retrieved["messages"]) == 0


# =============================================================================
# 3. Workspace round-trip
# =============================================================================
def test_workspace_upsert_and_retrieve(temp_db):
    """Upsert workspace, retrieve by hash, verify fields."""
    workspace = Workspace(
        workspace_hash="ws-unique-hash-123",
        folder_uri="file:///home/user/project",
        resolved_path="/home/user/project",
        first_seen_at=datetime.now(),
        last_seen_at=datetime.now(),
    )

    workspace_id = temp_db.upsert_workspace(workspace)
    assert workspace_id is not None

    # Retrieve by hash
    retrieved = temp_db.get_workspace_by_hash("ws-unique-hash-123")
    assert retrieved is not None
    assert retrieved["folder_uri"] == "file:///home/user/project"
    assert retrieved["resolved_path"] == "/home/user/project"

    # Upsert same hash returns same ID
    workspace_id_2 = temp_db.upsert_workspace(workspace)
    assert workspace_id == workspace_id_2


# =============================================================================
# 4. Project CRUD
# =============================================================================
def test_project_lifecycle(temp_db):
    """Create project, assign workspace, list, delete."""
    # Create project
    project_id = temp_db.create_project("Test Project", "A test project description")
    assert project_id is not None

    # Get project
    project = temp_db.get_project(project_id)
    assert project is not None
    assert project["name"] == "Test Project"
    assert project["description"] == "A test project description"

    # Get by name
    project_by_name = temp_db.get_project_by_name("Test Project")
    assert project_by_name is not None
    assert project_by_name["id"] == project_id

    # Create workspace and assign to project
    workspace = Workspace(workspace_hash="project-ws-001")
    workspace_id = temp_db.upsert_workspace(workspace)
    temp_db.assign_workspace_to_project(workspace_id, project_id)

    # List projects (should include workspace count)
    projects = temp_db.list_projects()
    assert len(projects) >= 1
    test_project = next((p for p in projects if p["id"] == project_id), None)
    assert test_project is not None

    # Get workspaces for project
    workspaces = temp_db.get_workspaces_by_project(project_id)
    assert len(workspaces) == 1

    # Delete project
    temp_db.delete_project(project_id)
    deleted_project = temp_db.get_project(project_id)
    assert deleted_project is None


# =============================================================================
# 5. Tag operations
# =============================================================================
def test_tag_add_remove_list(workspace_with_chat):
    """Add tags, remove some, list all tags with frequencies."""
    db = workspace_with_chat["db"]
    chat_id = workspace_with_chat["chat_id"]

    # Add tags
    db.add_tags(chat_id, ["python", "testing", "refactor"])

    # Get tags for chat
    tags = db.get_chat_tags(chat_id)
    assert len(tags) == 3
    assert "python" in tags
    assert "testing" in tags
    assert "refactor" in tags

    # Remove one tag
    db.remove_tags(chat_id, ["testing"])
    tags_after = db.get_chat_tags(chat_id)
    assert len(tags_after) == 2
    assert "testing" not in tags_after

    # Get all tags with frequency
    all_tags = db.get_all_tags()
    assert len(all_tags) >= 2


# =============================================================================
# 6. Search - instant
# =============================================================================
def test_instant_search_returns_results(temp_db):
    """Insert chat with known text, instant search finds it."""
    workspace = Workspace(workspace_hash="search-ws-001")
    workspace_id = temp_db.upsert_workspace(workspace)

    chat = Chat(
        cursor_composer_id="search-chat-001",
        workspace_id=workspace_id,
        title="Kubernetes Deployment Guide",
        messages=[
            Message(
                role=MessageRole.USER,
                text="How do I deploy to kubernetes?",
            ),
            Message(
                role=MessageRole.ASSISTANT,
                text="Here's how to create a kubernetes deployment...",
            ),
        ],
    )
    temp_db.upsert_chat(chat)

    # Instant search should find it
    results = temp_db.instant_search("kubernetes", limit=10)
    assert len(results) > 0

    # Check result structure (uses 'id' not 'chat_id')
    result = results[0]
    assert "id" in result
    assert "title" in result
    assert "snippet" in result


# =============================================================================
# 7. Search - filtered with tags
# =============================================================================
def test_search_filtered_with_tags(temp_db):
    """Search with tag filter returns only matching chats."""
    workspace = Workspace(workspace_hash="filter-ws-001")
    workspace_id = temp_db.upsert_workspace(workspace)

    # Create two chats
    chat1 = Chat(
        cursor_composer_id="filter-chat-001",
        workspace_id=workspace_id,
        title="Python Database",
        messages=[Message(role=MessageRole.USER, text="Python SQLite usage")],
    )
    chat1_id = temp_db.upsert_chat(chat1)
    temp_db.add_tags(chat1_id, ["python", "database"])

    chat2 = Chat(
        cursor_composer_id="filter-chat-002",
        workspace_id=workspace_id,
        title="JavaScript Frontend",
        messages=[Message(role=MessageRole.USER, text="React component design")],
    )
    chat2_id = temp_db.upsert_chat(chat2)
    temp_db.add_tags(chat2_id, ["javascript", "frontend"])

    # Search with python tag filter (need a query for FTS)
    results, total = temp_db.search_with_snippets_filtered(
        query="Python", tag_filters=["python"], limit=50
    )

    # Should only find the python chat (uses 'id' not 'chat_id')
    chat_ids = [r["id"] for r in results]
    assert chat1_id in chat_ids
    assert chat2_id not in chat_ids


# =============================================================================
# 8. Activity tracking
# =============================================================================
def test_activity_upsert_and_summary(temp_db):
    """Insert activity records, get summary, verify aggregation."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Insert activity records
    activities = [
        CursorActivity(
            date=today,
            kind="Included",
            model="claude-3-5-sonnet",
            input_tokens_with_cache=1000,
            output_tokens=500,
            total_tokens=1500,
            cost=0.05,
        ),
        CursorActivity(
            date=today,
            kind="Included",
            model="gpt-4o",
            input_tokens_with_cache=2000,
            output_tokens=1000,
            total_tokens=3000,
            cost=0.10,
        ),
    ]

    for activity in activities:
        temp_db.upsert_activity(activity)

    # Get summary without date filters (avoids SQL bug in get_activity_summary
    # with WHERE clause when filters are provided)
    summary = temp_db.get_activity_summary()

    assert summary is not None
    assert "total_cost" in summary
    assert summary["total_cost"] > 0


# =============================================================================
# 9. Ingestion state
# =============================================================================
def test_ingestion_state_round_trip(temp_db):
    """Store ingestion checkpoint, retrieve it, verify fields."""
    now = datetime.now()

    # Update ingestion state (stats are stored as separate columns, not dict)
    temp_db.update_ingestion_state(
        source="cursor",
        last_run_at=now,
        last_processed_timestamp=now,
        stats={"ingested": 42, "skipped": 5, "errors": 1},
    )

    # Retrieve state
    state = temp_db.get_ingestion_state("cursor")
    assert state is not None
    # Note: source is not returned in the dict, just used for lookup
    assert "last_run_at" in state
    assert state["stats_ingested"] == 42


# =============================================================================
# 10. Chat listing with pagination
# =============================================================================
def test_list_chats_pagination(temp_db):
    """Insert multiple chats, verify limit/offset work correctly."""
    workspace = Workspace(workspace_hash="pagination-ws")
    workspace_id = temp_db.upsert_workspace(workspace)

    # Create 10 chats
    for i in range(10):
        chat = Chat(
            cursor_composer_id=f"pagination-chat-{i:03d}",
            workspace_id=workspace_id,
            title=f"Pagination Test Chat {i}",
            messages=[Message(role=MessageRole.USER, text=f"Message {i}")],
        )
        temp_db.upsert_chat(chat)

    # Test limit
    chats_limit_5 = temp_db.list_chats(limit=5)
    assert len(chats_limit_5) == 5

    # Test offset
    chats_offset_5 = temp_db.list_chats(limit=5, offset=5)
    assert len(chats_offset_5) == 5

    # Ensure no overlap
    ids_first = {c["id"] for c in chats_limit_5}
    ids_second = {c["id"] for c in chats_offset_5}
    assert ids_first.isdisjoint(ids_second)

    # Count total
    total = temp_db.count_chats()
    assert total == 10


# =============================================================================
# 11. FTS index integrity
# =============================================================================
def test_fts_index_updated_on_upsert(temp_db):
    """Upsert chat, search immediately finds it in FTS."""
    workspace = Workspace(workspace_hash="fts-ws")
    workspace_id = temp_db.upsert_workspace(workspace)

    # Create chat with unique searchable term
    unique_term = "xyzzy12345uniqueterm"
    chat = Chat(
        cursor_composer_id="fts-test-chat",
        workspace_id=workspace_id,
        title=f"Chat about {unique_term}",
        messages=[
            Message(role=MessageRole.USER, text=f"Tell me about {unique_term}")
        ],
    )
    temp_db.upsert_chat(chat)

    # Search should immediately find it (FTS index updated)
    results = temp_db.instant_search(unique_term, limit=10)
    assert len(results) > 0
    assert unique_term.lower() in results[0]["title"].lower()


# =============================================================================
# 12. Plan linking
# =============================================================================
def test_plan_chat_linking(workspace_with_chat):
    """Create plan, link to chat, verify bidirectional retrieval."""
    db = workspace_with_chat["db"]
    chat_id = workspace_with_chat["chat_id"]

    # Create a plan - returns database ID (int), not plan_id string
    plan_db_id = db.upsert_plan(
        plan_id="plan-001",
        name="Refactoring Plan",
        file_path="plans/refactor.md",
        created_at=datetime.now(),
        last_updated_at=datetime.now(),
    )
    assert plan_db_id is not None

    # Link chat to plan using database ID
    db.link_chat_to_plan(chat_id, plan_db_id, relationship="created")

    # Get plans for chat
    plans = db.get_plans_for_chat(chat_id)
    assert len(plans) == 1
    assert plans[0]["plan_id"] == "plan-001"
    assert plans[0]["name"] == "Refactoring Plan"

    # Get chats for plan (uses database ID, not string plan_id)
    chats = db.get_chats_for_plan(plan_db_id)
    assert len(chats) == 1
    assert chats[0]["id"] == chat_id
