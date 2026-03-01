"""
Unit tests for ClaudeCodeReader session parsing.
"""

import json
from pathlib import Path

from src.readers.claude_code_reader import ClaudeCodeReader


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def test_read_session_follows_summary_leaf_uuid(tmp_path):
    """Reader should follow summary.leafUuid branch instead of naive traversal."""
    session_file = tmp_path / "sess-leaf.jsonl"
    rows = [
        {
            "type": "summary",
            "summary": "Leaf branch session",
            "leafUuid": "assist-side",
        },
        {
            "type": "user",
            "uuid": "user-root",
            "parentUuid": None,
            "sessionId": "sess-leaf",
            "timestamp": "2024-01-15T10:00:00Z",
            "message": {"role": "user", "content": "Start"},
        },
        {
            "type": "assistant",
            "uuid": "assist-main",
            "parentUuid": "user-root",
            "sessionId": "sess-leaf",
            "timestamp": "2024-01-15T10:00:03Z",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Main branch response"}],
            },
        },
        {
            "type": "assistant",
            "uuid": "assist-side",
            "parentUuid": "user-root",
            "sessionId": "sess-leaf",
            "timestamp": "2024-01-15T10:00:04Z",
            "isSidechain": True,
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Side branch response"}],
            },
        },
    ]
    _write_jsonl(session_file, rows)

    reader = ClaudeCodeReader(projects_path=tmp_path)
    session = reader.read_session(session_file)

    messages = session["messages"]
    assert [m["uuid"] for m in messages] == ["user-root", "assist-side"]
    assert messages[-1]["content"] == "Side branch response"


def test_read_session_extracts_structured_tool_results(tmp_path):
    """User tool_result blocks should retain structured metadata for downstream parsing."""
    session_file = tmp_path / "sess-tools.jsonl"
    rows = [
        {
            "type": "summary",
            "summary": "Tool result session",
            "leafUuid": "user-tool-result",
        },
        {
            "type": "user",
            "uuid": "user-tool-result",
            "parentUuid": None,
            "sessionId": "sess-tools",
            "timestamp": "2024-01-15T10:00:00Z",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_123",
                        "content": [
                            {"type": "text", "text": "line one"},
                            {"type": "text", "text": "line two"},
                        ],
                        "is_error": False,
                    }
                ],
            },
        },
    ]
    _write_jsonl(session_file, rows)

    reader = ClaudeCodeReader(projects_path=tmp_path)
    session = reader.read_session(session_file)

    assert len(session["messages"]) == 1
    msg = session["messages"][0]
    assert "[Tool Result]" in msg["content"]
    assert msg["tool_results"] is not None
    assert msg["tool_results"][0]["tool_use_id"] == "toolu_123"
    assert msg["tool_results"][0]["content"] == "line one\nline two"
    assert msg["tool_results"][0]["is_error"] is False
