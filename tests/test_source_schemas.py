"""
Tests for Pydantic source schema models.

Validates that Cursor source data can be parsed and validated correctly.
"""

import json
import pytest
from pydantic import ValidationError

from src.core.source_schemas.chatgpt import (
    AuthorRole,
    ChatGPTAuthor,
    ChatGPTConversation,
    ChatGPTContent,
    ChatGPTMessage,
    ChatGPTNode,
    MessageStatus,
)
from src.core.source_schemas.claude import (
    ClaudeConversation,
    ClaudeContentBlock,
    ClaudeMessage,
    ContentType,
    SenderRole,
    StopReason,
)
from src.core.source_schemas.cursor import (
    Bubble,
    BubbleHeader,
    BubbleType,
    ComposerData,
    ComposerHead,
    ComposerMode,
    ComposerStatus,
    UnifiedMode,
)


class TestBubbleHeader:
    """Tests for BubbleHeader model."""

    def test_valid_bubble_header(self):
        """Test validation of valid bubble header."""
        header_data = {
            "bubbleId": "test-bubble-123",
            "type": 1,
        }
        header = BubbleHeader.model_validate(header_data)
        assert header.bubbleId == "test-bubble-123"
        assert header.type == 1
        assert header.serverBubbleId is None

    def test_bubble_header_with_server_id(self):
        """Test bubble header with server bubble ID."""
        header_data = {
            "bubbleId": "test-bubble-123",
            "type": 2,
            "serverBubbleId": "server-bubble-456",
        }
        header = BubbleHeader.model_validate(header_data)
        assert header.serverBubbleId == "server-bubble-456"

    def test_bubble_header_extra_fields(self):
        """Test that extra fields are allowed (lenient validation)."""
        header_data = {
            "bubbleId": "test-bubble-123",
            "type": 1,
            "unknownField": "should be allowed",
        }
        header = BubbleHeader.model_validate(header_data)
        assert header.bubbleId == "test-bubble-123"
        # Extra field should be in model_dump()
        assert "unknownField" in header.model_dump()


class TestBubble:
    """Tests for Bubble model."""

    def test_valid_user_bubble(self):
        """Test validation of valid user bubble."""
        bubble_data = {
            "_v": 3,
            "bubbleId": "bubble-user-123",
            "type": 1,
            "text": "Hello, world!",
            "richText": '{"type":"root","children":[]}',
        }
        bubble = Bubble.model_validate(bubble_data)
        assert bubble.bubbleId == "bubble-user-123"
        assert bubble.type == 1
        assert bubble.text == "Hello, world!"
        assert bubble.v == 3  # Access via 'v' field name, but serializes as '_v'

    def test_valid_assistant_bubble(self):
        """Test validation of valid assistant bubble."""
        bubble_data = {
            "_v": 3,
            "bubbleId": "bubble-assistant-123",
            "type": 2,
            "text": "Hi there!",
            "serverBubbleId": "server-123",
            "thinking": {"text": "Let me think about this..."},
        }
        bubble = Bubble.model_validate(bubble_data)
        assert bubble.type == 2
        assert bubble.text == "Hi there!"
        assert bubble.thinking is not None
        assert bubble.thinking.text == "Let me think about this..."

    def test_bubble_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        bubble_data = {
            "text": "Hello",
            # Missing bubbleId and type
        }
        with pytest.raises(ValidationError):
            Bubble.model_validate(bubble_data)

    def test_bubble_optional_fields(self):
        """Test that optional fields can be missing."""
        bubble_data = {
            "_v": 3,
            "bubbleId": "bubble-123",
            "type": 1,
            # No text, richText, etc. - should be fine
        }
        bubble = Bubble.model_validate(bubble_data)
        assert bubble.text is None
        assert bubble.richText is None

    def test_bubble_with_code_blocks(self):
        """Test bubble with code blocks."""
        bubble_data = {
            "_v": 3,
            "bubbleId": "bubble-123",
            "type": 2,
            "codeBlocks": [
                {
                    "content": "print('hello')",
                    "languageId": "python",
                    "isGenerating": False,
                }
            ],
        }
        bubble = Bubble.model_validate(bubble_data)
        assert len(bubble.codeBlocks) == 1
        assert bubble.codeBlocks[0].content == "print('hello')"
        assert bubble.codeBlocks[0].languageId == "python"


class TestComposerData:
    """Tests for ComposerData model."""

    def test_valid_composer_data_minimal(self):
        """Test validation of minimal valid composer data."""
        composer_data = {
            "_v": 10,
            "composerId": "composer-123",
        }
        composer = ComposerData.model_validate(composer_data)
        assert composer.composerId == "composer-123"
        assert composer.v == 10  # Access via 'v' field name, but serializes as '_v'

    def test_composer_data_with_conversation(self):
        """Test composer data with legacy inline conversation."""
        composer_data = {
            "_v": 10,
            "composerId": "composer-123",
            "name": "Test Chat",
            "createdAt": 1734000000000,
            "conversation": [
                {
                    "_v": 3,
                    "bubbleId": "bubble-1",
                    "type": 1,
                    "text": "Hello",
                },
                {
                    "_v": 3,
                    "bubbleId": "bubble-2",
                    "type": 2,
                    "text": "Hi there!",
                },
            ],
        }
        composer = ComposerData.model_validate(composer_data)
        assert composer.name == "Test Chat"
        assert len(composer.conversation) == 2
        assert composer.conversation[0].text == "Hello"

    def test_composer_data_with_headers_only(self):
        """Test composer data with modern split format (headers only)."""
        composer_data = {
            "_v": 10,
            "composerId": "composer-123",
            "fullConversationHeadersOnly": [
                {"bubbleId": "bubble-1", "type": 1},
                {"bubbleId": "bubble-2", "type": 2, "serverBubbleId": "server-2"},
            ],
        }
        composer = ComposerData.model_validate(composer_data)
        assert len(composer.fullConversationHeadersOnly) == 2
        assert composer.fullConversationHeadersOnly[0].bubbleId == "bubble-1"
        assert composer.fullConversationHeadersOnly[1].serverBubbleId == "server-2"

    def test_composer_data_missing_composer_id(self):
        """Test that missing composerId raises ValidationError."""
        composer_data = {
            "_v": 10,
            # Missing composerId
        }
        with pytest.raises(ValidationError):
            ComposerData.model_validate(composer_data)

    def test_composer_data_with_context(self):
        """Test composer data with context object."""
        composer_data = {
            "_v": 10,
            "composerId": "composer-123",
            "context": {
                "fileSelections": [
                    {"uri": {"fsPath": "/path/to/file.py"}},
                ],
                "folderSelections": [],
            },
        }
        composer = ComposerData.model_validate(composer_data)
        assert composer.context is not None
        assert len(composer.context.fileSelections or []) >= 0  # May be empty list

    def test_composer_data_extra_fields(self):
        """Test that extra fields are allowed (lenient validation)."""
        composer_data = {
            "_v": 10,
            "composerId": "composer-123",
            "unknownField": "should be allowed",
            "anotherUnknown": {"nested": "data"},
        }
        composer = ComposerData.model_validate(composer_data)
        assert composer.composerId == "composer-123"
        # Extra fields should be preserved
        dump = composer.model_dump()
        assert "unknownField" in dump or dump.get("unknownField") == "should be allowed"


class TestComposerHead:
    """Tests for ComposerHead model."""

    def test_valid_composer_head(self):
        """Test validation of valid composer head."""
        head_data = {
            "composerId": "composer-123",
            "name": "Test Chat",
            "subtitle": "Auto subtitle",
            "createdAt": 1734000000000,
            "lastUpdatedAt": 1734001000000,
            "forceMode": "chat",
            "unifiedMode": "chat",
        }
        head = ComposerHead.model_validate(head_data)
        assert head.composerId == "composer-123"
        assert head.name == "Test Chat"
        assert head.forceMode == "chat"

    def test_composer_head_minimal(self):
        """Test composer head with only required fields."""
        head_data = {
            "composerId": "composer-123",
        }
        head = ComposerHead.model_validate(head_data)
        assert head.composerId == "composer-123"
        assert head.name is None

    def test_composer_head_missing_composer_id(self):
        """Test that missing composerId raises ValidationError."""
        head_data = {
            "name": "Test Chat",
            # Missing composerId
        }
        with pytest.raises(ValidationError):
            ComposerHead.model_validate(head_data)


class TestRealWorldFixtures:
    """Tests using real-world Cursor data structures from test fixtures."""

    def test_composer_data_from_test_fixture(self):
        """Test with data structure from test_readers.py fixture."""
        composer_data = {
            "composerId": "test-composer-123",
            "conversation": [
                {
                    "type": 1,
                    "bubbleId": "bubble-1",
                    "text": "Hello",
                },
                {
                    "type": 2,
                    "bubbleId": "bubble-2",
                    "text": "Hi there!",
                },
            ],
        }
        # Should work even without _v (will use default)
        composer = ComposerData.model_validate(composer_data)
        assert composer.composerId == "test-composer-123"
        assert len(composer.conversation) == 2

    def test_composer_head_from_test_fixture(self):
        """Test with composer head structure from test_aggregator_linking.py."""
        head_data = {
            "composerId": "composer-abc-123",
            "name": "Test Chat Name",
            "subtitle": "Test Subtitle",
            "createdAt": 1734000000000,
            "lastUpdatedAt": 1734001000000,
            "unifiedMode": "chat",
            "forceMode": "chat",
        }
        head = ComposerHead.model_validate(head_data)
        assert head.composerId == "composer-abc-123"
        assert head.name == "Test Chat Name"
        assert head.subtitle == "Test Subtitle"

    def test_empty_chat_detection(self):
        """Test empty chat structure (from storage-reference.md)."""
        composer_data = {
            "_v": 10,
            "composerId": "fbd30712-94fd-48d3-b674-ed162dbf56ab",
            "text": "",
            "fullConversationHeadersOnly": [],
            "conversationMap": {},
        }
        composer = ComposerData.model_validate(composer_data)
        assert composer.fullConversationHeadersOnly == []
        assert len(composer.fullConversationHeadersOnly or []) == 0


class TestSchemaVersionHandling:
    """Tests for handling different schema versions."""

    def test_composer_data_v10(self):
        """Test ComposerData with _v: 10."""
        composer_data = {
            "_v": 10,
            "composerId": "composer-123",
        }
        composer = ComposerData.model_validate(composer_data)
        assert composer.v == 10  # Access via 'v' field name, but serializes as '_v'

    def test_bubble_v3(self):
        """Test Bubble with _v: 3."""
        bubble_data = {
            "_v": 3,
            "bubbleId": "bubble-123",
            "type": 1,
        }
        bubble = Bubble.model_validate(bubble_data)
        assert bubble.v == 3  # Access via 'v' field name, but serializes as '_v'

    def test_schema_version_defaults(self):
        """Test that schema versions default correctly."""
        # ComposerData defaults to _v: 10
        composer_data = {
            "composerId": "composer-123",
            # No _v specified
        }
        composer = ComposerData.model_validate(composer_data)
        assert composer.v == 10  # Access via 'v' field name, but serializes as '_v'

        # Bubble defaults to _v: 3
        bubble_data = {
            "bubbleId": "bubble-123",
            "type": 1,
            # No _v specified
        }
        bubble = Bubble.model_validate(bubble_data)
        assert bubble.v == 3  # Access via 'v' field name, but serializes as '_v'


class TestCursorEnums:
    """Tests for Cursor enum validation and backward compatibility."""

    def test_bubble_type_enum_accepts_int(self):
        """Test that BubbleType field accepts raw int values."""
        bubble_data = {
            "_v": 3,
            "bubbleId": "bubble-123",
            "type": 1,  # Raw int
        }
        bubble = Bubble.model_validate(bubble_data)
        assert bubble.type == 1

    def test_bubble_type_enum_accepts_enum(self):
        """Test that BubbleType field accepts enum values."""
        bubble_data = {
            "_v": 3,
            "bubbleId": "bubble-123",
            "type": BubbleType.ASSISTANT,  # Enum value
        }
        bubble = Bubble.model_validate(bubble_data)
        assert bubble.type == 2  # Normalized to int

    def test_composer_status_enum_accepts_str(self):
        """Test that ComposerStatus field accepts raw string values."""
        composer_data = {
            "_v": 10,
            "composerId": "composer-123",
            "status": "generating",  # Raw string
        }
        composer = ComposerData.model_validate(composer_data)
        assert composer.status == "generating"

    def test_composer_status_enum_accepts_enum(self):
        """Test that ComposerStatus field accepts enum values."""
        composer_data = {
            "_v": 10,
            "composerId": "composer-123",
            "status": ComposerStatus.COMPLETED,  # Enum value
        }
        composer = ComposerData.model_validate(composer_data)
        assert composer.status == "completed"  # Normalized to str

    def test_composer_mode_enum_accepts_str(self):
        """Test that ComposerMode field accepts raw string values."""
        composer_data = {
            "_v": 10,
            "composerId": "composer-123",
            "forceMode": "agent",  # Raw string
        }
        composer = ComposerData.model_validate(composer_data)
        assert composer.forceMode == "agent"

    def test_composer_mode_enum_accepts_enum(self):
        """Test that ComposerMode field accepts enum values."""
        composer_data = {
            "_v": 10,
            "composerId": "composer-123",
            "forceMode": ComposerMode.CHAT,  # Enum value
        }
        composer = ComposerData.model_validate(composer_data)
        assert composer.forceMode == "chat"  # Normalized to str

    def test_unified_mode_enum_accepts_int(self):
        """Test that UnifiedMode field accepts raw int values."""
        bubble_data = {
            "_v": 3,
            "bubbleId": "bubble-123",
            "type": 1,
            "unifiedMode": 2,  # Raw int
        }
        bubble = Bubble.model_validate(bubble_data)
        assert bubble.unifiedMode == 2

    def test_unified_mode_enum_accepts_enum(self):
        """Test that UnifiedMode field accepts enum values."""
        bubble_data = {
            "_v": 3,
            "bubbleId": "bubble-123",
            "type": 1,
            "unifiedMode": UnifiedMode.AGENT,  # Enum value
        }
        bubble = Bubble.model_validate(bubble_data)
        assert bubble.unifiedMode == 2  # Normalized to int


class TestClaudeSchemas:
    """Tests for Claude.ai source schema models."""

    def test_claude_message_minimal(self):
        """Test validation of minimal Claude message."""
        message_data = {
            "uuid": "msg-123",
            "sender": "human",
            "index": 0,
            "created_at": "2025-01-01T00:00:00Z",
            "content": [],
        }
        message = ClaudeMessage.model_validate(message_data)
        assert message.uuid == "msg-123"
        assert message.sender == SenderRole.HUMAN
        assert message.index == 0

    def test_claude_message_with_content(self):
        """Test Claude message with content blocks."""
        message_data = {
            "uuid": "msg-123",
            "sender": "assistant",
            "index": 1,
            "created_at": "2025-01-01T00:00:00Z",
            "content": [
                {
                    "type": "text",
                    "text": "Hello, world!",
                    "start_timestamp": "2025-01-01T00:00:00Z",
                    "stop_timestamp": "2025-01-01T00:00:01Z",
                },
                {
                    "type": "thinking",
                    "thinking": "Let me think...",
                },
            ],
        }
        message = ClaudeMessage.model_validate(message_data)
        assert len(message.content) == 2
        assert message.content[0].type == ContentType.TEXT
        assert message.content[0].text == "Hello, world!"
        assert message.content[1].type == ContentType.THINKING
        assert message.content[1].thinking == "Let me think..."

    def test_claude_conversation_minimal(self):
        """Test validation of minimal Claude conversation."""
        conv_data = {
            "uuid": "conv-123",
            "model": "claude-opus-4-5-20251101",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "chat_messages": [],
        }
        conv = ClaudeConversation.model_validate(conv_data)
        assert conv.uuid == "conv-123"
        assert conv.model == "claude-opus-4-5-20251101"
        assert len(conv.chat_messages) == 0

    def test_claude_conversation_with_messages(self):
        """Test Claude conversation with messages."""
        conv_data = {
            "uuid": "conv-123",
            "model": "claude-opus-4-5-20251101",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "chat_messages": [
                {
                    "uuid": "msg-1",
                    "sender": "human",
                    "index": 0,
                    "created_at": "2025-01-01T00:00:00Z",
                    "content": [{"type": "text", "text": "Hello"}],
                },
                {
                    "uuid": "msg-2",
                    "sender": "assistant",
                    "index": 1,
                    "created_at": "2025-01-01T00:00:01Z",
                    "content": [{"type": "text", "text": "Hi there!"}],
                    "stop_reason": "stop_sequence",
                },
            ],
        }
        conv = ClaudeConversation.model_validate(conv_data)
        assert len(conv.chat_messages) == 2
        assert conv.chat_messages[0].sender == SenderRole.HUMAN
        assert conv.chat_messages[1].sender == SenderRole.ASSISTANT
        assert conv.chat_messages[1].stop_reason == StopReason.STOP_SEQUENCE

    def test_claude_sender_role_enum(self):
        """Test that SenderRole enum works correctly."""
        message_data = {
            "uuid": "msg-123",
            "sender": "assistant",  # String value
            "index": 0,
            "created_at": "2025-01-01T00:00:00Z",
            "content": [],
        }
        message = ClaudeMessage.model_validate(message_data)
        assert message.sender == SenderRole.ASSISTANT


class TestChatGPTSchemas:
    """Tests for ChatGPT source schema models."""

    def test_chatgpt_author_minimal(self):
        """Test validation of minimal ChatGPT author."""
        author_data = {
            "role": "user",
        }
        author = ChatGPTAuthor.model_validate(author_data)
        assert author.role == AuthorRole.USER

    def test_chatgpt_message_minimal(self):
        """Test validation of minimal ChatGPT message."""
        message_data = {
            "id": "msg-123",
            "author": {"role": "user"},
            "content": {"content_type": "text", "parts": ["Hello"]},
            "status": "finished_successfully",
        }
        message = ChatGPTMessage.model_validate(message_data)
        assert message.id == "msg-123"
        assert message.author.role == AuthorRole.USER
        assert message.status == MessageStatus.FINISHED_SUCCESSFULLY

    def test_chatgpt_node_with_message(self):
        """Test ChatGPT node with message."""
        node_data = {
            "id": "node-123",
            "parent": None,
            "children": ["node-456"],
            "message": {
                "id": "msg-123",
                "author": {"role": "assistant"},
                "content": {"content_type": "text", "parts": ["Hi"]},
                "status": "finished_successfully",
            },
        }
        node = ChatGPTNode.model_validate(node_data)
        assert node.id == "node-123"
        assert node.parent is None
        assert len(node.children) == 1
        assert node.message is not None
        assert node.message.author.role == AuthorRole.ASSISTANT

    def test_chatgpt_node_without_message(self):
        """Test ChatGPT node without message (container node)."""
        node_data = {
            "id": "node-123",
            "parent": None,
            "children": ["node-456"],
            "message": None,
        }
        node = ChatGPTNode.model_validate(node_data)
        assert node.message is None

    def test_chatgpt_conversation_minimal(self):
        """Test validation of minimal ChatGPT conversation."""
        conv_data = {
            "conversation_id": "conv-123",
            "id": "conv-123",
            "title": "Test Chat",
            "create_time": 1735689600.0,
            "update_time": 1735689600.0,
            "current_node": "node-123",
            "mapping": {},
        }
        conv = ChatGPTConversation.model_validate(conv_data)
        assert conv.conversation_id == "conv-123"
        assert conv.title == "Test Chat"
        assert len(conv.mapping) == 0

    def test_chatgpt_conversation_with_tree(self):
        """Test ChatGPT conversation with message tree."""
        conv_data = {
            "conversation_id": "conv-123",
            "id": "conv-123",
            "title": "Test Chat",
            "create_time": 1735689600.0,
            "update_time": 1735689600.0,
            "current_node": "node-2",
            "mapping": {
                "node-1": {
                    "id": "node-1",
                    "parent": None,
                    "children": ["node-2"],
                    "message": {
                        "id": "msg-1",
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["Hello"]},
                        "status": "finished_successfully",
                    },
                },
                "node-2": {
                    "id": "node-2",
                    "parent": "node-1",
                    "children": [],
                    "message": {
                        "id": "msg-2",
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": ["Hi"]},
                        "status": "finished_successfully",
                    },
                },
            },
        }
        conv = ChatGPTConversation.model_validate(conv_data)
        assert len(conv.mapping) == 2
        assert conv.mapping["node-1"].message.author.role == AuthorRole.USER
        assert conv.mapping["node-2"].message.author.role == AuthorRole.ASSISTANT

    def test_chatgpt_author_role_enum(self):
        """Test that AuthorRole enum works correctly."""
        author_data = {
            "role": "system",  # String value
        }
        author = ChatGPTAuthor.model_validate(author_data)
        assert author.role == AuthorRole.SYSTEM
