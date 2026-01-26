"""
Unit tests for ClaudeCodeTransformer.

Tests the transformation of raw Claude Code session data to Chat domain models.
"""
import pytest
from datetime import datetime

from src.core.models import Chat, ChatMode, MessageRole, MessageType
from src.transformers.claude_code import ClaudeCodeTransformer


@pytest.fixture
def transformer():
    """Create a ClaudeCodeTransformer instance for testing."""
    # For unit tests, we don't need actual RawStorage or domain_db
    # The transform() method only uses raw_data dict
    return ClaudeCodeTransformer(raw_storage=None, domain_db=None)


def test_source_name(transformer):
    """Test that source_name returns 'claude-code'."""
    assert transformer.source_name == "claude-code"


def test_transform_basic_session(transformer):
    """Test transforming a basic Claude Code session to Chat."""
    raw_data = {
        "session_id": "sess-123",
        "summary": "Test Session",
        "messages": [
            {
                "role": "user",
                "content": "Hello, how are you?",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-1",
            },
            {
                "role": "assistant",
                "content": "I'm doing well, thank you!",
                "timestamp": "2024-01-15T10:00:05Z",
                "uuid": "msg-2",
                "model": "claude-3-5-sonnet-20241022",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert isinstance(chat, Chat)
    assert chat.cursor_composer_id == "sess-123"
    assert chat.title == "Test Session"
    assert chat.source == "claude-code"
    assert chat.summary == "Test Session"
    assert len(chat.messages) == 2
    assert chat.mode == ChatMode.CHAT


def test_transform_extracts_messages(transformer):
    """Test that user/assistant roles are correctly mapped."""
    raw_data = {
        "session_id": "sess-456",
        "summary": "Role Test",
        "messages": [
            {
                "role": "user",
                "content": "User message",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-user",
            },
            {
                "role": "assistant",
                "content": "Assistant message",
                "timestamp": "2024-01-15T10:00:05Z",
                "uuid": "msg-assistant",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 2
    assert chat.messages[0].role == MessageRole.USER
    assert chat.messages[0].text == "User message"
    assert chat.messages[1].role == MessageRole.ASSISTANT
    assert chat.messages[1].text == "Assistant message"


def test_transform_extracts_thinking(transformer):
    """Test that thinking content is prepended with [Thinking]."""
    raw_data = {
        "session_id": "sess-thinking",
        "summary": "Thinking Test",
        "messages": [
            {
                "role": "assistant",
                "content": "Here's my response",
                "thinking": "Let me think about this...",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-thinking",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 1
    message = chat.messages[0]
    assert "[Thinking]" in message.text
    assert message.text.startswith("[Thinking]")
    assert "Let me think about this..." in message.text
    assert "Here's my response" in message.text
    assert message.message_type == MessageType.THINKING


def test_transform_extracts_tool_calls(transformer):
    """Test that tool calls are formatted with [Tool: name]."""
    raw_data = {
        "session_id": "sess-tools",
        "summary": "Tool Test",
        "messages": [
            {
                "role": "assistant",
                "content": "I'll use a tool",
                "tool_calls": [
                    {"name": "read_file", "arguments": {}},
                    {"name": "write_file", "arguments": {}},
                ],
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-tools",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 1
    message = chat.messages[0]
    assert "[Tool: read_file]" in message.text
    assert "[Tool: write_file]" in message.text
    assert message.message_type == MessageType.TOOL_CALL


def test_transform_calculates_cost(transformer):
    """Test that estimated_cost is calculated from token usage."""
    raw_data = {
        "session_id": "sess-cost",
        "summary": "Cost Test",
        "messages": [
            {
                "role": "user",
                "content": "Test",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-user",
            },
            {
                "role": "assistant",
                "content": "Response",
                "model": "claude-3-5-sonnet-20241022",
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                },
                "timestamp": "2024-01-15T10:00:05Z",
                "uuid": "msg-assistant",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert chat.estimated_cost is not None
    # Sonnet pricing: $3/1M input, $15/1M output
    # Expected: (1000 * 3 + 500 * 15) / 1_000_000 = 0.0105
    expected_cost = (1000 * 3 + 500 * 15) / 1_000_000
    assert abs(chat.estimated_cost - expected_cost) < 0.0001


def test_transform_calculates_cost_opus(transformer):
    """Test that Opus model uses different pricing."""
    raw_data = {
        "session_id": "sess-opus",
        "summary": "Opus Cost Test",
        "messages": [
            {
                "role": "assistant",
                "content": "Response",
                "model": "claude-3-opus-20240229",
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                },
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-opus",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert chat.estimated_cost is not None
    # Opus pricing: $15/1M input, $75/1M output
    # Expected: (1000 * 15 + 500 * 75) / 1_000_000 = 0.0525
    expected_cost = (1000 * 15 + 500 * 75) / 1_000_000
    assert abs(chat.estimated_cost - expected_cost) < 0.0001


def test_transform_determines_mode(transformer):
    """Test that mode is AGENT when tool_calls present, CHAT otherwise."""
    # Test CHAT mode (no tool calls)
    raw_data_chat = {
        "session_id": "sess-chat",
        "summary": "Chat Mode",
        "messages": [
            {
                "role": "user",
                "content": "Hello",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-1",
            },
            {
                "role": "assistant",
                "content": "Hi there",
                "timestamp": "2024-01-15T10:00:05Z",
                "uuid": "msg-2",
            },
        ],
    }

    chat_chat = transformer.transform(raw_data_chat)
    assert chat_chat is not None
    assert chat_chat.mode == ChatMode.CHAT

    # Test AGENT mode (with tool calls)
    raw_data_agent = {
        "session_id": "sess-agent",
        "summary": "Agent Mode",
        "messages": [
            {
                "role": "user",
                "content": "Do something",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-1",
            },
            {
                "role": "assistant",
                "content": "I'll use a tool",
                "tool_calls": [{"name": "read_file", "arguments": {}}],
                "timestamp": "2024-01-15T10:00:05Z",
                "uuid": "msg-2",
            },
        ],
    }

    chat_agent = transformer.transform(raw_data_agent)
    assert chat_agent is not None
    assert chat_agent.mode == ChatMode.AGENT


def test_transform_returns_none_for_missing_session_id(transformer):
    """Test that transform returns None if session_id is missing."""
    raw_data = {
        "summary": "No Session ID",
        "messages": [
            {
                "role": "user",
                "content": "Test",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-1",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is None


def test_transform_returns_none_for_empty_session_id(transformer):
    """Test that transform returns None if session_id is empty string."""
    raw_data = {
        "session_id": "",
        "summary": "Empty Session ID",
        "messages": [
            {
                "role": "user",
                "content": "Test",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-1",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is None


def test_transform_extracts_title_from_slug(transformer):
    """Test that title is extracted from metadata.slug when no summary."""
    raw_data = {
        "session_id": "sess-slug",
        "metadata": {
            "slug": "my-awesome-session",
        },
        "messages": [
            {
                "role": "user",
                "content": "Test",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-1",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert chat.title == "My Awesome Session"  # slug converted to title case


def test_transform_uses_summary_over_slug(transformer):
    """Test that summary takes precedence over slug."""
    raw_data = {
        "session_id": "sess-priority",
        "summary": "Summary Title",
        "metadata": {
            "slug": "slug-title",
        },
        "messages": [
            {
                "role": "user",
                "content": "Test",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-1",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert chat.title == "Summary Title"


def test_transform_uses_untitled_when_no_summary_or_slug(transformer):
    """Test that 'Untitled Session' is used when neither summary nor slug exists."""
    raw_data = {
        "session_id": "sess-untitled",
        "messages": [
            {
                "role": "user",
                "content": "Test",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-1",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert chat.title == "Untitled Session"


def test_transform_parses_timestamps(transformer):
    """Test that timestamps are correctly parsed from ISO format."""
    raw_data = {
        "session_id": "sess-time",
        "summary": "Time Test",
        "messages": [
            {
                "role": "user",
                "content": "Test",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-1",
            },
            {
                "role": "assistant",
                "content": "Response",
                "timestamp": "2024-01-15T10:05:30Z",
                "uuid": "msg-2",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert chat.created_at is not None
    assert chat.last_updated_at is not None
    assert isinstance(chat.created_at, datetime)
    assert isinstance(chat.last_updated_at, datetime)
    assert chat.last_updated_at > chat.created_at


def test_transform_skips_empty_sessions(transformer):
    """Test that sessions with no messages return None."""
    raw_data = {
        "session_id": "sess-empty",
        "summary": "Empty Session",
        "messages": [],
    }

    chat = transformer.transform(raw_data)

    assert chat is None


def test_transform_skips_unknown_roles(transformer):
    """Test that messages with unknown roles are skipped."""
    raw_data = {
        "session_id": "sess-unknown",
        "summary": "Unknown Role",
        "messages": [
            {
                "role": "system",
                "content": "System message",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-system",
            },
            {
                "role": "user",
                "content": "User message",
                "timestamp": "2024-01-15T10:00:05Z",
                "uuid": "msg-user",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    # Only user message should be included
    assert len(chat.messages) == 1
    assert chat.messages[0].role == MessageRole.USER


def test_transform_handles_thinking_without_content(transformer):
    """Test that thinking without content still works."""
    raw_data = {
        "session_id": "sess-thinking-only",
        "summary": "Thinking Only",
        "messages": [
            {
                "role": "assistant",
                "thinking": "Just thinking...",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-thinking",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 1
    message = chat.messages[0]
    assert message.text == "[Thinking]\nJust thinking..."
    assert message.message_type == MessageType.THINKING


def test_transform_handles_tool_calls_without_content(transformer):
    """Test that tool calls without content still work."""
    raw_data = {
        "session_id": "sess-tools-only",
        "summary": "Tools Only",
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [{"name": "read_file", "arguments": {}}],
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-tools",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 1
    message = chat.messages[0]
    assert message.text == "[Tool: read_file]"
    assert message.message_type == MessageType.TOOL_CALL


def test_transform_accumulates_token_usage(transformer):
    """Test that token usage is accumulated across multiple assistant messages."""
    raw_data = {
        "session_id": "sess-accumulate",
        "summary": "Accumulate Tokens",
        "messages": [
            {
                "role": "user",
                "content": "Question 1",
                "timestamp": "2024-01-15T10:00:00Z",
                "uuid": "msg-1",
            },
            {
                "role": "assistant",
                "content": "Answer 1",
                "model": "claude-3-5-sonnet-20241022",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                },
                "timestamp": "2024-01-15T10:00:05Z",
                "uuid": "msg-2",
            },
            {
                "role": "user",
                "content": "Question 2",
                "timestamp": "2024-01-15T10:01:00Z",
                "uuid": "msg-3",
            },
            {
                "role": "assistant",
                "content": "Answer 2",
                "model": "claude-3-5-sonnet-20241022",
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 100,
                },
                "timestamp": "2024-01-15T10:01:05Z",
                "uuid": "msg-4",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert chat.estimated_cost is not None
    # Total: input_tokens=300, output_tokens=150
    # Expected: (300 * 3 + 150 * 15) / 1_000_000 = 0.00315
    expected_cost = (300 * 3 + 150 * 15) / 1_000_000
    assert abs(chat.estimated_cost - expected_cost) < 0.0001
