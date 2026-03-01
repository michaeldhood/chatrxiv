"""
Unit tests for chat API parsing helpers.
"""

from src.api.routes.chats import (
    classify_tool_call,
    extract_file_paths_from_tool_calls,
    extract_terminal_commands,
    extract_terminal_result_blocks,
    is_terminal_only_tool_message,
)


def test_classify_tool_call_handles_claude_code_terminal_tool():
    """Claude Code Bash tool calls should classify as terminal."""
    msg = {
        "raw_json": {
            "tool_calls": [
                {
                    "id": "toolu_123",
                    "name": "Bash",
                    "input": {"command": "ls -la"},
                }
            ]
        }
    }

    result = classify_tool_call(msg)

    assert result["tool_type"] == "terminal"
    assert result["tool_name"] == "Terminal Command"
    assert result["tool_description"] == "ls -la"


def test_extract_terminal_commands_handles_claude_code_tool_calls():
    """Terminal command extraction should support Claude Code tool_calls format."""
    raw_json = {
        "tool_calls": [
            {
                "id": "toolu_abc",
                "name": "Bash",
                "input": {"command": "git status"},
            }
        ]
    }

    commands = extract_terminal_commands(raw_json, created_at="2024-01-15T10:00:00Z")

    assert len(commands) == 1
    assert commands[0]["command"] == "git status"
    assert commands[0]["tool_use_id"] == "toolu_abc"
    assert commands[0]["created_at"] == "2024-01-15T10:00:00Z"


def test_extract_terminal_result_blocks_handles_tool_results():
    """Terminal result extraction should read output from tool_results arrays."""
    raw_json = {
        "tool_results": [
            {
                "tool_use_id": "toolu_abc",
                "content": [{"type": "text", "text": "On branch main"}],
                "is_error": False,
            }
        ]
    }

    results = extract_terminal_result_blocks(raw_json)

    assert len(results) == 1
    assert results[0]["tool_use_id"] == "toolu_abc"
    assert results[0]["output"] == "On branch main"
    assert results[0]["status"] == "completed"


def test_is_terminal_only_tool_message_for_claude_code_shapes():
    """Terminal-only tool call and tool result messages should be skipped from tool groups."""
    terminal_tool_call = {
        "tool_calls": [
            {"id": "toolu_1", "name": "Bash", "input": {"command": "pwd"}}
        ]
    }
    terminal_tool_result = {
        "tool_results": [
            {"tool_use_id": "toolu_1", "content": "repo/path", "is_error": False}
        ]
    }
    mixed_tools = {
        "tool_calls": [
            {"id": "toolu_1", "name": "Bash", "input": {"command": "pwd"}},
            {"id": "toolu_2", "name": "ReadFile", "input": {"path": "README.md"}},
        ]
    }

    assert is_terminal_only_tool_message(terminal_tool_call) is True
    assert is_terminal_only_tool_message(terminal_tool_result) is True
    assert is_terminal_only_tool_message(mixed_tools) is False


def test_extract_file_paths_handles_claude_code_input_payloads():
    """File-path extraction should include Claude Code tool input payloads."""
    raw_json = {
        "tool_calls": [
            {"name": "ReadFile", "input": {"path": "src/main.py"}},
            {"name": "Edit", "input": {"file": "docs/notes.md"}},
            {"name": "EditNotebook", "input": {"target_notebook": "analysis.ipynb"}},
        ]
    }

    paths = extract_file_paths_from_tool_calls(raw_json)

    assert "src/main.py" in paths
    assert "docs/notes.md" in paths
    assert "analysis.ipynb" in paths
