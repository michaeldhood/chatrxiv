"""
Unit tests for ClaudeTransformer.

Tests the transformation of raw Claude.ai conversation data to Chat domain models.
"""
import pytest
from datetime import datetime
from unittest.mock import Mock

from src.transformers.claude import ClaudeTransformer
from src.core.models import Chat, MessageRole, MessageType, ChatMode


@pytest.fixture
def transformer():
    """Create a ClaudeTransformer instance with mocked dependencies."""
    mock_raw_storage = Mock()
    mock_domain_db = Mock()
    return ClaudeTransformer(mock_raw_storage, mock_domain_db)


def test_source_name(transformer):
    """Test that source_name returns 'claude.ai'."""
    assert transformer.source_name == "claude.ai"


def test_transform_basic_conversation(transformer):
    """Test transforming a basic Claude conversation to Chat."""
    raw_data = {
        "uuid": "conv-123",
        "name": "Test Conversation",
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T11:00:00Z",
        "model": "claude-3-5-sonnet-20241022",
        "chat_messages": [
            {
                "uuid": "msg-1",
                "sender": "human",
                "content": [{"type": "text", "text": "Hello, Claude!"}],
                "created_at": "2024-01-15T10:30:00Z",
            },
            {
                "uuid": "msg-2",
                "sender": "assistant",
                "content": [{"type": "text", "text": "Hello! How can I help you?"}],
                "created_at": "2024-01-15T10:30:05Z",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert isinstance(chat, Chat)
    assert chat.cursor_composer_id == "conv-123"
    assert chat.title == "Test Conversation"
    assert chat.source == "claude.ai"
    assert chat.model == "claude-3-5-sonnet-20241022"
    assert chat.mode == ChatMode.CHAT
    assert len(chat.messages) == 2


def test_transform_extracts_messages(transformer):
    """Test that human->USER and assistant->ASSISTANT mapping works correctly."""
    raw_data = {
        "uuid": "conv-456",
        "name": "Role Test",
        "chat_messages": [
            {
                "uuid": "msg-1",
                "sender": "human",
                "content": [{"type": "text", "text": "User message"}],
            },
            {
                "uuid": "msg-2",
                "sender": "assistant",
                "content": [{"type": "text", "text": "Assistant message"}],
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


def test_transform_extracts_text_from_content_blocks(transformer):
    """Test that text is correctly extracted from content blocks array."""
    raw_data = {
        "uuid": "conv-789",
        "name": "Content Extraction Test",
        "chat_messages": [
            {
                "uuid": "msg-1",
                "sender": "assistant",
                "content": [
                    {"type": "text", "text": "First paragraph"},
                    {"type": "text", "text": "Second paragraph"},
                    {"type": "image", "source": {"data": "base64..."}},  # Should be skipped
                ],
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 1
    # Text blocks should be joined with double newlines
    assert chat.messages[0].text == "First paragraph\n\nSecond paragraph"


def test_transform_parses_timestamps(transformer):
    """Test that ISO timestamps with 'Z' suffix are parsed correctly."""
    raw_data = {
        "uuid": "conv-timestamp",
        "name": "Timestamp Test",
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T11:00:00Z",
        "chat_messages": [
            {
                "uuid": "msg-1",
                "sender": "human",
                "content": [{"type": "text", "text": "Test"}],
                "created_at": "2024-01-15T10:30:05Z",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert isinstance(chat.created_at, datetime)
    assert isinstance(chat.last_updated_at, datetime)
    assert isinstance(chat.messages[0].created_at, datetime)
    
    # Verify timestamps are parsed correctly (Z should be converted to +00:00)
    assert chat.created_at.year == 2024
    assert chat.created_at.month == 1
    assert chat.created_at.day == 15


def test_transform_extracts_title(transformer):
    """Test that title is extracted from name or summary fields."""
    # Test with name field
    raw_data1 = {
        "uuid": "conv-1",
        "name": "Conversation Name",
        "chat_messages": [],
    }
    chat1 = transformer.transform(raw_data1)
    assert chat1 is not None
    assert chat1.title == "Conversation Name"

    # Test with summary field (when name is missing)
    raw_data2 = {
        "uuid": "conv-2",
        "summary": "Conversation Summary",
        "chat_messages": [],
    }
    chat2 = transformer.transform(raw_data2)
    assert chat2 is not None
    assert chat2.title == "Conversation Summary"

    # Test fallback to "Untitled Chat"
    raw_data3 = {
        "uuid": "conv-3",
        "chat_messages": [],
    }
    chat3 = transformer.transform(raw_data3)
    assert chat3 is not None
    assert chat3.title == "Untitled Chat"


def test_transform_returns_none_for_missing_uuid(transformer):
    """Test that transform returns None when uuid is missing."""
    raw_data = {
        "name": "No UUID",
        "chat_messages": [],
    }

    chat = transformer.transform(raw_data)

    assert chat is None


def test_transform_handles_empty_messages(transformer):
    """Test handling of conversations with no messages."""
    raw_data = {
        "uuid": "conv-empty",
        "name": "Empty Conversation",
        "created_at": "2024-01-15T10:30:00Z",
        "chat_messages": [],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 0
    assert chat.cursor_composer_id == "conv-empty"
    assert chat.title == "Empty Conversation"


def test_transform_skips_unknown_sender_types(transformer):
    """Test that messages with unknown sender types are skipped."""
    raw_data = {
        "uuid": "conv-unknown",
        "name": "Unknown Sender Test",
        "chat_messages": [
            {
                "uuid": "msg-1",
                "sender": "human",
                "content": [{"type": "text", "text": "Valid message"}],
            },
            {
                "uuid": "msg-2",
                "sender": "unknown_type",
                "content": [{"type": "text", "text": "Should be skipped"}],
            },
            {
                "uuid": "msg-3",
                "sender": "assistant",
                "content": [{"type": "text", "text": "Another valid message"}],
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    # Should only have 2 messages (unknown sender skipped)
    assert len(chat.messages) == 2
    assert chat.messages[0].text == "Valid message"
    assert chat.messages[1].text == "Another valid message"


def test_transform_handles_missing_content(transformer):
    """Test handling of messages with missing or empty content."""
    raw_data = {
        "uuid": "conv-missing-content",
        "name": "Missing Content Test",
        "chat_messages": [
            {
                "uuid": "msg-1",
                "sender": "human",
                "content": [],  # Empty content array
            },
            {
                "uuid": "msg-2",
                "sender": "assistant",
                "text": "Fallback text field",  # Fallback to text field
            },
            {
                "uuid": "msg-3",
                "sender": "assistant",
                # No content or text field
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 3
    
    # First message should have empty text
    assert chat.messages[0].text == ""
    assert chat.messages[0].message_type == MessageType.EMPTY
    
    # Second message should use fallback text field
    assert chat.messages[1].text == "Fallback text field"
    
    # Third message should have empty text
    assert chat.messages[2].text == ""
    assert chat.messages[2].message_type == MessageType.EMPTY


def test_transform_message_timestamp_fallback(transformer):
    """Test that message timestamp falls back to conversation created_at."""
    raw_data = {
        "uuid": "conv-fallback",
        "name": "Timestamp Fallback Test",
        "created_at": "2024-01-15T10:30:00Z",
        "chat_messages": [
            {
                "uuid": "msg-1",
                "sender": "human",
                "content": [{"type": "text", "text": "No timestamp"}],
                # No created_at field
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 1
    # Message timestamp should fall back to conversation created_at
    assert chat.messages[0].created_at == chat.created_at


def test_transform_handles_invalid_timestamps(transformer):
    """Test handling of invalid timestamp formats."""
    raw_data = {
        "uuid": "conv-invalid-time",
        "name": "Invalid Timestamp Test",
        "created_at": "not-a-valid-timestamp",
        "updated_at": "2024-01-15T11:00:00Z",
        "chat_messages": [
            {
                "uuid": "msg-1",
                "sender": "human",
                "content": [{"type": "text", "text": "Test"}],
                "created_at": "also-invalid",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    # Invalid timestamps should result in None
    assert chat.created_at is None
    assert chat.last_updated_at is not None  # This one was valid
    assert chat.messages[0].created_at is None


def test_transform_multiple_content_blocks(transformer):
    """Test extraction of text from multiple content blocks."""
    raw_data = {
        "uuid": "conv-multi-block",
        "name": "Multiple Blocks Test",
        "chat_messages": [
            {
                "uuid": "msg-1",
                "sender": "assistant",
                "content": [
                    {"type": "text", "text": "Block 1"},
                    {"type": "text", "text": "Block 2"},
                    {"type": "text", "text": "Block 3"},
                ],
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 1
    expected_text = "Block 1\n\nBlock 2\n\nBlock 3"
    assert chat.messages[0].text == expected_text
