"""
Integration tests for FastAPI API routes.
"""

import asyncio
import os

from fastapi.testclient import TestClient

from src.api.deps import get_db
from src.api.main import app
from src.api.routes.stream import stream


def test_get_chats_returns_paginated_results(api_client):
    response = api_client.get("/api/chats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["page"] == 1
    assert payload["limit"] == 50
    assert len(payload["chats"]) == 3
    assert payload["chats"][0]["title"] == "Database activity chat"
    assert payload["chats"][1]["title"] == "Python search chat"
    assert payload["chats"][2]["title"] == "Legacy Empty Chat"


def test_get_chats_supports_filter_and_pagination(api_client):
    response = api_client.get("/api/chats", params={"filter": "non_empty", "limit": 1, "page": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["filter"] == "non_empty"
    assert payload["total"] == 2
    assert len(payload["chats"]) == 1
    assert payload["chats"][0]["messages_count"] > 0


def test_get_chat_returns_chat_detail(api_client):
    response = api_client.get("/api/chats/1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == 1
    assert payload["title"] == "Python search chat"
    assert payload["messages_count"] == 2
    assert payload["plans"][0]["name"] == "Launch plan"
    assert payload["processed_messages"]


def test_get_chat_supports_message_limit(api_client):
    response = api_client.get("/api/chats/1", params={"message_limit": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_messages"] == 2
    assert payload["pagination"]["requested_offset"] == 0
    assert payload["pagination"]["requested_limit"] == 1
    assert payload["pagination"]["covered_start"] == 0
    assert payload["pagination"]["covered_end"] == 1
    assert payload["pagination"]["has_more"] is True
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["role"] == "user"


def test_get_chat_supports_message_offset(api_client):
    response = api_client.get(
        "/api/chats/1",
        params={"message_offset": 1, "message_limit": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_messages"] == 2
    assert payload["pagination"]["requested_offset"] == 1
    assert payload["pagination"]["requested_limit"] == 1
    assert payload["pagination"]["covered_start"] == 1
    assert payload["pagination"]["covered_end"] == 2
    assert payload["pagination"]["has_previous"] is True
    assert payload["pagination"]["has_more"] is False
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["role"] == "assistant"


def test_get_chat_returns_404_for_missing_chat(api_client):
    response = api_client.get("/api/chats/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Chat not found"}


def test_post_chats_bulk_returns_requested_chats(api_client):
    response = api_client.post("/api/chats/bulk", json={"chat_ids": [2, 1]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested"] == 2
    assert payload["found"] == 2
    assert [chat["id"] for chat in payload["chats"]] == [2, 1]


def test_post_chats_bulk_rejects_empty_payload(api_client):
    response = api_client.post("/api/chats/bulk", json={"chat_ids": []})

    assert response.status_code == 422


def test_post_chats_bulk_rejects_too_many_ids(api_client):
    response = api_client.post("/api/chats/bulk", json={"chat_ids": list(range(101))})

    assert response.status_code == 422


def test_search_returns_results_for_valid_query(api_client):
    response = api_client.get("/api/search", params={"q": "python"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "python"
    assert payload["total"] == 1
    assert payload["results"][0]["title"] == "Python search chat"


def test_search_requires_non_empty_query(api_client):
    response = api_client.get("/api/search", params={"q": ""})

    assert response.status_code == 422


def test_search_rejects_invalid_sort(api_client):
    response = api_client.get("/api/search", params={"q": "python", "sort": "invalid"})

    assert response.status_code == 422


def test_instant_search_returns_results(api_client):
    response = api_client.get("/api/instant-search", params={"q": "py"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "py"
    assert payload["count"] >= 1
    assert payload["results"][0]["snippet"]


def test_instant_search_returns_empty_for_short_query(api_client):
    response = api_client.get("/api/instant-search", params={"q": "p"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 0
    assert payload["results"] == []


def test_search_facets_returns_facets(api_client):
    response = api_client.get("/api/search/facets", params={"q": "python"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "python"
    assert "tech/python" in payload["tag_facets"]
    assert payload["workspace_facets"]


def test_search_facets_supports_filters(api_client):
    response = api_client.get(
        "/api/search/facets",
        params=[("q", "python"), ("tags", "tech/python"), ("workspaces", 1)],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_filters"] == ["tech/python"]
    assert payload["active_workspace_filters"] == [1]
    assert payload["total"] == 1


def test_filter_options_returns_sources_and_modes(api_client):
    response = api_client.get("/api/filter-options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"]
    assert payload["modes"]
    assert {source["value"] for source in payload["sources"]} >= {"cursor", "legacy"}


def test_settings_returns_database_runtime_and_sources(api_client):
    response = api_client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["database"]["chats_db_path"].endswith(".db")
    assert payload["database"]["raw_db_path"].endswith("raw.db")
    assert payload["runtime"]["watch_enabled"] is False
    assert isinstance(payload["settings"], list)
    assert {entry["key"] for entry in payload["settings"]} >= {
        "source.cursor.workspace_storage_path",
        "source.claude_code.projects_path",
        "source.claude.export_path",
        "source.chatgpt.export_path",
    }
    assert len(payload["ingestion"]) == 4
    assert {row["source"] for row in payload["ingestion"]} == {
        "cursor",
        "claude.ai",
        "chatgpt",
        "claude-code",
    }


def test_post_ingest_accepts_background_job(api_client):
    response = api_client.post(
        "/api/ingest",
        json={"mode": "incremental", "sources": ["cursor", "claude-code"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "accepted": True,
        "message": "Ingestion started in background",
        "mode": "incremental",
        "sources": ["cursor", "claude-code"],
    }


def test_health_returns_ready_status_and_request_id(api_client):
    response = api_client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert "X-Request-ID" in response.headers


def test_health_echoes_client_request_id(api_client):
    response = api_client.get("/api/health", headers={"X-Request-ID": "test-request-id"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-id"


def test_activity_returns_records(api_client):
    response = api_client.get("/api/activity")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert {record["model"] for record in payload} == {
        "claude-3-5-sonnet",
        "claude-3-haiku",
    }


def test_activity_supports_pagination(api_client):
    response = api_client.get("/api/activity", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["model"] == "claude-3-5-sonnet"


def test_activity_summary_returns_aggregate(api_client):
    response = api_client.get("/api/activity/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_cost"] > 0
    assert payload["total_tokens"] == 640


def test_activity_daily_returns_chart_data(api_client):
    response = api_client.get("/api/activity/daily")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["date"] == "2026-04-01"
    assert payload[1]["date"] == "2026-04-02"


def test_stream_returns_initial_connected_event():
    async def consume_first_event() -> str:
        response = await stream()
        first_chunk = await anext(response.body_iterator)
        if hasattr(response.body_iterator, "aclose"):
            await response.body_iterator.aclose()
        return first_chunk.decode() if isinstance(first_chunk, bytes) else first_chunk

    first_event = asyncio.run(consume_first_event())

    assert first_event == 'data: {"type": "connected"}\n\n'


def test_unhandled_exception_returns_structured_error(api_client):
    def broken_db_dependency():
        raise RuntimeError("boom")
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = broken_db_dependency
    try:
        response = api_client.get("/api/search", params={"q": "python"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert payload["error"]["message"] == "An unexpected error occurred"
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]


def test_http_exception_is_not_wrapped(api_client):
    response = api_client.get("/api/chats/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Chat not found"}


def test_validation_errors_keep_default_shape(api_client):
    response = api_client.get("/api/search")

    assert response.status_code == 422
    payload = response.json()
    assert "detail" in payload


def test_activity_route_uses_safe_error_message(api_client):
    class ExplodingActivityDb:
        def close(self):
            return None

        def get_activity_by_date_range(self, *args, **kwargs):
            raise RuntimeError("sensitive database failure")

    def exploding_db_dependency():
        yield ExplodingActivityDb()

    app.dependency_overrides[get_db] = exploding_db_dependency
    try:
        response = api_client.get("/api/activity")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to fetch activity records"}


def test_summarize_route_uses_safe_missing_key_message(api_client):
    previous_api_key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        response = api_client.post("/api/chats/1/summarize")
    finally:
        if previous_api_key is not None:
            os.environ["ANTHROPIC_API_KEY"] = previous_api_key

    assert response.status_code == 503
    assert response.json() == {"detail": "Summarization is not configured"}


def test_status_reports_existing_data(api_client):
    response = api_client.get("/api/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["has_data"] is True
    assert payload["chat_count"] == 3
    assert len(payload["sources"]) == 4
    cursor_source = next(source for source in payload["sources"] if source["name"] == "cursor")
    assert cursor_source["chat_count"] == 1
    assert "runtime" in payload
    assert payload["runtime"]["manual_ingest"]["running"] is False


def test_status_reports_empty_database(temp_db):
    os.environ["CHATRXIV_WATCH"] = "false"

    def override_get_db():
        yield temp_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/api/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["has_data"] is False
    assert payload["chat_count"] == 0
