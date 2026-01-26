"""
Unit tests for ChatGPTTransformer.

Tests the transformation of raw ChatGPT conversation data into Chat domain models.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from src.core.db import ChatDatabase
from src.core.db.raw_storage import RawStorage
from src.core.models import Chat, ChatMode, MessageRole, MessageType
from src.transformers.chatgpt import ChatGPTTransformer


@pytest.fixture
def mock_raw_storage():
    """Create a mock RawStorage for testing."""
    return MagicMock(spec=RawStorage)


@pytest.fixture
def mock_domain_db():
    """Create a mock ChatDatabase for testing."""
    return MagicMock(spec=ChatDatabase)


@pytest.fixture
def transformer(mock_raw_storage, mock_domain_db):
    """Create a ChatGPTTransformer instance for testing."""
    return ChatGPTTransformer(mock_raw_storage, mock_domain_db)


def test_source_name(transformer):
    """Test that source_name property returns 'chatgpt'."""
    assert transformer.source_name == "chatgpt"


def test_transform_basic_conversation(transformer):
    """Test transforming a basic ChatGPT conversation to Chat."""
    raw_data = {
        "id": "conv-123",
        "title": "Test Conversation",
        "create_time": 1766681665.991872,
        "update_time": 1766681765.991872,
        "chat_messages": [
            {
                "sender": "user",
                "content": [{"type": "text", "text": "Hello, how are you?"}],
                "created_at": 1766681665.991872,
                "uuid": "msg-user-1",
            },
            {
                "sender": "assistant",
                "content": [{"type": "text", "text": "I'm doing well, thank you!"}],
                "created_at": 1766681700.991872,
                "uuid": "msg-assistant-1",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert isinstance(chat, Chat)
    assert chat.cursor_composer_id == "conv-123"
    assert chat.title == "Test Conversation"
    assert chat.source == "chatgpt"
    assert chat.mode == ChatMode.CHAT
    assert chat.workspace_id is None
    assert len(chat.messages) == 2


def test_transform_extracts_messages(transformer):
    """Test that user->USER and assistant->ASSISTANT role mapping works."""
    raw_data = {
        "id": "conv-456",
        "title": "Role Test",
        "chat_messages": [
            {
                "sender": "user",
                "content": [{"type": "text", "text": "User message"}],
                "uuid": "msg-1",
            },
            {
                "sender": "assistant",
                "content": [{"type": "text", "text": "Assistant message"}],
                "uuid": "msg-2",
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


def test_transform_parses_unix_timestamps(transformer):
    """Test that Unix epoch float timestamps are parsed correctly."""
    unix_timestamp = 1766681665.991872
    raw_data = {
        "id": "conv-789",
        "title": "Unix Timestamp Test",
        "create_time": unix_timestamp,
        "update_time": unix_timestamp + 100,
        "chat_messages": [
            {
                "sender": "user",
                "content": [{"type": "text", "text": "Test"}],
                "created_at": unix_timestamp,
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert chat.created_at is not None
    assert isinstance(chat.created_at, datetime)
    assert chat.last_updated_at is not None
    assert isinstance(chat.last_updated_at, datetime)
    assert chat.messages[0].created_at is not None
    assert isinstance(chat.messages[0].created_at, datetime)


def test_transform_parses_iso_timestamps(transformer):
    """Test that ISO string timestamps are parsed correctly."""
    iso_timestamp = "2025-12-30T22:12:41.767145Z"
    raw_data = {
        "id": "conv-iso",
        "title": "ISO Timestamp Test",
        "create_time": iso_timestamp,
        "update_time": "2025-12-30T22:13:41.767145Z",
        "chat_messages": [
            {
                "sender": "user",
                "content": [{"type": "text", "text": "Test"}],
                "created_at": iso_timestamp,
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert chat.created_at is not None
    assert isinstance(chat.created_at, datetime)
    assert chat.last_updated_at is not None
    assert isinstance(chat.last_updated_at, datetime)
    assert chat.messages[0].created_at is not None
    assert isinstance(chat.messages[0].created_at, datetime)


def test_transform_extracts_text_from_content(transformer):
    """Test that text is correctly extracted from content array."""
    raw_data = {
        "id": "conv-content",
        "title": "Content Extraction Test",
        "chat_messages": [
            {
                "sender": "user",
                "content": [
                    {"type": "text", "text": "First line"},
                    {"type": "text", "text": "Second line"},
                ],
                "uuid": "msg-1",
            },
            {
                "sender": "assistant",
                "content": ["Simple string content"],
                "uuid": "msg-2",
            },
        ],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 2
    assert chat.messages[0].text == "First line\nSecond line"
    assert chat.messages[1].text == "Simple string content"


def test_transform_extracts_title(transformer):
    """Test that title is extracted correctly."""
    raw_data = {
        "id": "conv-title",
        "title": "My Custom Title",
        "chat_messages": [],
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert chat.title == "My Custom Title"

    # Test default title when missing
    raw_data_no_title = {
        "id": "conv-no-title",
        "chat_messages": [],
    }

    chat_no_title = transformer.transform(raw_data_no_title)

    assert chat_no_title is not None
    assert chat_no_title.title == "Untitled Chat"


def test_transform_returns_none_for_missing_id(transformer):
    """Test that transform returns None when id is missing."""
    raw_data_no_id = {
        "title": "No ID",
        "chat_messages": [],
    }

    result = transformer.transform(raw_data_no_id)

    assert result is None

    # Test with empty id
    raw_data_empty_id = {
        "id": "",
        "title": "Empty ID",
        "chat_messages": [],
    }

    result_empty = transformer.transform(raw_data_empty_id)

    assert result_empty is None
