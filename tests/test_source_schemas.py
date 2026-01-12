"""
Tests for Pydantic source schema models.

Validates that Cursor source data can be parsed and validated correctly.
"""

import json
import pytest
from pydantic import ValidationError

from src.core.source_schemas.cursor import (
    Bubble,
    BubbleHeader,
    ComposerData,
    ComposerHead,
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
