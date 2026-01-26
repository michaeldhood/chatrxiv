"""
Unit tests for CursorTransformer.

Tests transformation of raw Cursor composer data to Chat domain models.
"""
import pytest
import tempfile
import os
from datetime import datetime
from unittest.mock import Mock, MagicMock

from src.core.db import ChatDatabase, RawStorage
from src.core.models import Chat, ChatMode, MessageRole, MessageType
from src.transformers.cursor import CursorTransformer
from src.readers.global_reader import GlobalComposerReader


@pytest.fixture
def temp_storage():
    """Create a temporary RawStorage for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    storage = RawStorage(path)
    yield storage
    storage.close()
    # Clean up WAL files too
    for suffix in ['', '-wal', '-shm']:
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


@pytest.fixture
def temp_db():
    """Create a temporary ChatDatabase for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = ChatDatabase(path)
    yield db
    db.close()
    # Clean up WAL files too
    for suffix in ['', '-wal', '-shm']:
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


@pytest.fixture
def transformer(temp_storage, temp_db):
    """Create a CursorTransformer instance."""
    return CursorTransformer(temp_storage, temp_db)


@pytest.fixture
def transformer_with_reader(temp_storage, temp_db):
    """Create a CursorTransformer with mocked GlobalComposerReader."""
    mock_reader = Mock(spec=GlobalComposerReader)
    return CursorTransformer(temp_storage, temp_db, global_reader=mock_reader)


def test_source_name(transformer):
    """Test that source_name returns 'cursor'."""
    assert transformer.source_name == "cursor"


def test_transform_basic_conversation(transformer):
    """Test transforming raw composer data with conversation array to Chat."""
    composer_id = "test-composer-123"
    raw_data = {
        "composer_id": composer_id,
        "data": {
            "composerId": composer_id,
            "forceMode": "chat",
            "name": "Test Chat",
            "createdAt": 1704067200000,  # 2024-01-01 00:00:00 UTC
            "lastUpdatedAt": 1704067800000,  # 2024-01-01 00:10:00 UTC
            "conversation": [
                {
                    "bubbleId": "bubble-1",
                    "type": 1,  # User message
                    "text": "Hello, how are you?",
                    "richText": "",
                    "createdAt": "2024-01-01T00:00:00Z",
                },
                {
                    "bubbleId": "bubble-2",
                    "type": 2,  # Assistant message
                    "text": "I'm doing well, thank you!",
                    "richText": "",
                    "createdAt": "2024-01-01T00:00:05Z",
                },
            ],
        },
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert isinstance(chat, Chat)
    assert chat.cursor_composer_id == composer_id
    assert chat.title == "Test Chat"
    assert chat.mode == ChatMode.CHAT
    assert chat.source == "cursor"
    assert len(chat.messages) == 2

    # Check first message (user)
    assert chat.messages[0].role == MessageRole.USER
    assert chat.messages[0].text == "Hello, how are you?"
    assert chat.messages[0].cursor_bubble_id == "bubble-1"
    assert chat.messages[0].message_type == MessageType.RESPONSE

    # Check second message (assistant)
    assert chat.messages[1].role == MessageRole.ASSISTANT
    assert chat.messages[1].text == "I'm doing well, thank you!"
    assert chat.messages[1].cursor_bubble_id == "bubble-2"
    assert chat.messages[1].message_type == MessageType.RESPONSE


def test_transform_headers_only(transformer_with_reader):
    """Test transforming data with fullConversationHeadersOnly format."""
    composer_id = "test-composer-456"
    
    # Mock the global reader to return bubble content
    bubble_1_content = {
        "bubbleId": "bubble-1",
        "type": 1,
        "text": "User question",
        "richText": "",
    }
    bubble_2_content = {
        "bubbleId": "bubble-2",
        "type": 2,
        "text": "Assistant response",
        "richText": "",
    }
    
    transformer_with_reader.global_reader.read_bubbles_batch = Mock(
        return_value={
            "bubble-1": bubble_1_content,
            "bubble-2": bubble_2_content,
        }
    )

    raw_data = {
        "composer_id": composer_id,
        "data": {
            "composerId": composer_id,
            "forceMode": "chat",
            "name": "Headers Only Chat",
            "fullConversationHeadersOnly": [
                {"bubbleId": "bubble-1", "type": 1},
                {"bubbleId": "bubble-2", "type": 2},
            ],
        },
    }

    chat = transformer_with_reader.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 2
    assert chat.messages[0].text == "User question"
    assert chat.messages[1].text == "Assistant response"
    
    # Verify global reader was called
    transformer_with_reader.global_reader.read_bubbles_batch.assert_called_once_with(
        composer_id, ["bubble-1", "bubble-2"]
    )


def test_transform_extracts_messages(transformer):
    """Test that messages are correctly extracted with roles."""
    composer_id = "test-composer-789"
    raw_data = {
        "composer_id": composer_id,
        "data": {
            "composerId": composer_id,
            "conversation": [
                {
                    "bubbleId": "user-1",
                    "type": 1,  # User
                    "text": "What is Python?",
                },
                {
                    "bubbleId": "assistant-1",
                    "type": 2,  # Assistant
                    "text": "Python is a programming language.",
                },
                {
                    "bubbleId": "user-2",
                    "type": 1,  # User
                    "text": "Thanks!",
                },
            ],
        },
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert len(chat.messages) == 3
    
    assert chat.messages[0].role == MessageRole.USER
    assert chat.messages[0].text == "What is Python?"
    
    assert chat.messages[1].role == MessageRole.ASSISTANT
    assert chat.messages[1].text == "Python is a programming language."
    
    assert chat.messages[2].role == MessageRole.USER
    assert chat.messages[2].text == "Thanks!"


def test_transform_extracts_timestamps(transformer):
    """Test that created_at and last_updated_at are correctly parsed."""
    composer_id = "test-composer-timestamps"
    created_at_ms = 1704067200000  # 2024-01-01 00:00:00 UTC
    updated_at_ms = 1704067800000  # 2024-01-01 00:10:00 UTC
    
    raw_data = {
        "composer_id": composer_id,
        "data": {
            "composerId": composer_id,
            "createdAt": created_at_ms,
            "lastUpdatedAt": updated_at_ms,
            "conversation": [
                {
                    "bubbleId": "bubble-1",
                    "type": 1,
                    "text": "Test",
                    "createdAt": "2024-01-01T00:00:00Z",
                },
            ],
        },
    }

    chat = transformer.transform(raw_data)

    assert chat is not None
    assert chat.created_at is not None
    assert chat.last_updated_at is not None
    
    # Verify timestamps are parsed correctly (milliseconds to datetime)
    expected_created = datetime.fromtimestamp(created_at_ms / 1000)
    expected_updated = datetime.fromtimestamp(updated_at_ms / 1000)
    
    assert chat.created_at == expected_created
    assert chat.last_updated_at == expected_updated


def test_transform_extracts_title(transformer):
    """Test that title is extracted from name/subtitle."""
    composer_id = "test-composer-title"
    
    # Test with name
    raw_data = {
        "composer_id": composer_id,
        "data": {
            "composerId": composer_id,
            "name": "My Chat Title",
            "conversation": [],
        },
    }
    
    chat = transformer.transform(raw_data)
    assert chat is not None
    assert chat.title == "My Chat Title"
    
    # Test with subtitle when name is missing
    raw_data2 = {
        "composer_id": composer_id + "-2",
        "data": {
            "composerId": composer_id + "-2",
            "subtitle": "My Subtitle",
            "conversation": [],
        },
    }
    
    chat2 = transformer.transform(raw_data2)
    assert chat2 is not None
    assert chat2.title == "My Subtitle"
    
    # Test with composer_head name (priority)
    raw_data3 = {
        "composer_id": composer_id + "-3",
        "composer_head": {
            "name": "Workspace Title",
        },
        "data": {
            "composerId": composer_id + "-3",
            "name": "Global Title",
            "conversation": [],
        },
    }
    
    chat3 = transformer.transform(raw_data3)
    assert chat3 is not None
    assert chat3.title == "Workspace Title"  # Workspace head takes priority
    
    # Test fallback to "Untitled Chat"
    raw_data4 = {
        "composer_id": composer_id + "-4",
        "data": {
            "composerId": composer_id + "-4",
            "conversation": [],
        },
    }
    
    chat4 = transformer.transform(raw_data4)
    assert chat4 is not None
    assert chat4.title == "Untitled Chat"


def test_transform_returns_none_for_invalid(transformer):
    """Test that transform returns None for data without composerId."""
    # Missing composer_id
    raw_data1 = {
        "data": {
            "composerId": "test-123",
            "conversation": [],
        },
    }
    assert transformer.transform(raw_data1) is None
    
    # Missing data field
    raw_data2 = {
        "composer_id": "test-123",
    }
    assert transformer.transform(raw_data2) is None
    
    # Missing composerId in data
    raw_data3 = {
        "composer_id": "test-123",
        "data": {
            "conversation": [],
        },
    }
    assert transformer.transform(raw_data3) is None


def test_transform_skips_empty_messages(transformer):
    """Test that chats with no messages return None or are handled."""
    composer_id = "test-composer-empty"
    
    # Empty conversation array
    raw_data1 = {
        "composer_id": composer_id,
        "data": {
            "composerId": composer_id,
            "conversation": [],
        },
    }
    
    chat1 = transformer.transform(raw_data1)
    assert chat1 is not None  # Chat is created, but with no messages
    assert len(chat1.messages) == 0
    
    # Conversation with only unknown bubble types (type != 1 or 2)
    raw_data2 = {
        "composer_id": composer_id + "-2",
        "data": {
            "composerId": composer_id + "-2",
            "conversation": [
                {
                    "bubbleId": "bubble-unknown",
                    "type": 99,  # Unknown type
                    "text": "Should be skipped",
                },
            ],
        },
    }
    
    chat2 = transformer.transform(raw_data2)
    assert chat2 is not None
    assert len(chat2.messages) == 0  # Unknown types are skipped


def test_transform_with_workspace_id(transformer):
    """Test that workspace_id is correctly extracted and set."""
    composer_id = "test-composer-workspace"
    workspace_id = 42
    
    raw_data = {
        "composer_id": composer_id,
        "workspace_id": workspace_id,
        "data": {
            "composerId": composer_id,
            "conversation": [
                {
                    "bubbleId": "bubble-1",
                    "type": 1,
                    "text": "Test",
                },
            ],
        },
    }
    
    chat = transformer.transform(raw_data)
    assert chat is not None
    assert chat.workspace_id == workspace_id


def test_transform_with_relevant_files(transformer):
    """Test that relevant files are extracted from bubbles."""
    composer_id = "test-composer-files"
    
    raw_data = {
        "composer_id": composer_id,
        "data": {
            "composerId": composer_id,
            "conversation": [
                {
                    "bubbleId": "bubble-1",
                    "type": 1,
                    "text": "Check this file",
                    "relevantFiles": ["/path/to/file1.py", "/path/to/file2.ts"],
                },
                {
                    "bubbleId": "bubble-2",
                    "type": 2,
                    "text": "I'll check it",
                    "relevantFiles": ["/path/to/file1.py"],
                },
            ],
        },
    }
    
    chat = transformer.transform(raw_data)
    assert chat is not None
    assert len(chat.relevant_files) == 2
    assert "/path/to/file1.py" in chat.relevant_files
    assert "/path/to/file2.ts" in chat.relevant_files


def test_transform_with_thinking_content(transformer):
    """Test that thinking content is extracted when text is empty."""
    composer_id = "test-composer-thinking"
    
    raw_data = {
        "composer_id": composer_id,
        "data": {
            "composerId": composer_id,
            "conversation": [
                {
                    "bubbleId": "bubble-1",
                    "type": 2,
                    "text": "",  # Empty text
                    "thinking": {
                        "text": "Let me think about this...",
                    },
                },
            ],
        },
    }
    
    chat = transformer.transform(raw_data)
    assert chat is not None
    assert len(chat.messages) == 1
    assert chat.messages[0].text == "Let me think about this..."


def test_transform_mode_mapping(transformer):
    """Test that different modes are correctly mapped."""
    composer_id = "test-composer-mode"
    
    modes_to_test = [
        ("chat", ChatMode.CHAT),
        ("edit", ChatMode.EDIT),
        ("agent", ChatMode.AGENT),
        ("composer", ChatMode.COMPOSER),
        ("plan", ChatMode.PLAN),
        ("debug", ChatMode.DEBUG),
        ("ask", ChatMode.ASK),
    ]
    
    for mode_str, expected_mode in modes_to_test:
        raw_data = {
            "composer_id": f"{composer_id}-{mode_str}",
            "data": {
                "composerId": f"{composer_id}-{mode_str}",
                "forceMode": mode_str,
                "conversation": [
                    {
                        "bubbleId": "bubble-1",
                        "type": 1,
                        "text": "Test",
                    },
                ],
            },
        }
        
        chat = transformer.transform(raw_data)
        assert chat is not None
        assert chat.mode == expected_mode


def test_transform_headers_only_without_reader(transformer):
    """Test headers-only format when GlobalComposerReader is not available."""
    composer_id = "test-composer-headers-no-reader"
    
    raw_data = {
        "composer_id": composer_id,
        "data": {
            "composerId": composer_id,
            "fullConversationHeadersOnly": [
                {"bubbleId": "bubble-1", "type": 1},
                {"bubbleId": "bubble-2", "type": 2},
            ],
        },
    }
    
    chat = transformer.transform(raw_data)
    assert chat is not None
    # Should create messages from headers, but without text content
    assert len(chat.messages) == 2
    assert chat.messages[0].text == ""  # No text since reader not available
    assert chat.messages[1].text == ""


def test_transform_message_type_classification(transformer):
    """Test that message types are correctly classified."""
    composer_id = "test-composer-types"
    
    # Response type (has text)
    raw_data1 = {
        "composer_id": composer_id + "-1",
        "data": {
            "composerId": composer_id + "-1",
            "conversation": [
                {
                    "bubbleId": "bubble-1",
                    "type": 2,
                    "text": "Response text",
                },
            ],
        },
    }
    chat1 = transformer.transform(raw_data1)
    assert chat1.messages[0].message_type == MessageType.RESPONSE
    
    # Tool call type (has codeBlock but no text)
    raw_data2 = {
        "composer_id": composer_id + "-2",
        "data": {
            "composerId": composer_id + "-2",
            "conversation": [
                {
                    "bubbleId": "bubble-2",
                    "type": 2,
                    "text": "",
                    "codeBlock": {"content": "print('hello')"},
                },
            ],
        },
    }
    chat2 = transformer.transform(raw_data2)
    assert chat2.messages[0].message_type == MessageType.TOOL_CALL
    
    # Empty type (no text, no tool fields)
    raw_data3 = {
        "composer_id": composer_id + "-3",
        "data": {
            "composerId": composer_id + "-3",
            "conversation": [
                {
                    "bubbleId": "bubble-3",
                    "type": 2,
                    "text": "",
                },
            ],
        },
    }
    chat3 = transformer.transform(raw_data3)
    assert chat3.messages[0].message_type == MessageType.EMPTY
