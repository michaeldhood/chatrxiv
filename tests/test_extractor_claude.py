"""
Unit tests for ClaudeExtractor.

Tests extraction of Claude.ai conversations, storage in RawStorage,
and error handling scenarios.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock

from src.extractors.claude import ClaudeExtractor
from src.core.db import RawStorage


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
def mock_claude_reader():
    """Create a mock ClaudeReader for testing."""
    reader = Mock()
    return reader


@pytest.fixture
def fake_conversation_meta():
    """Sample conversation metadata from Claude API."""
    return {
        "uuid": "conv-123",
        "name": "Test Chat",
        "created_at": "2024-01-01T00:00:00Z",
    }


@pytest.fixture
def fake_conversation_detail():
    """Sample full conversation detail from Claude API."""
    return {
        "uuid": "conv-123",
        "name": "Test Chat",
        "created_at": "2024-01-01T00:00:00Z",
        "chat_messages": [
            {
                "role": "user",
                "content": "Hello, Claude!",
            },
            {
                "role": "assistant",
                "content": "Hello! How can I help you?",
            },
        ],
    }


def test_source_name(temp_storage, mock_claude_reader):
    """Test that source_name property returns 'claude.ai'."""
    with patch('src.extractors.claude.ClaudeReader', return_value=mock_claude_reader):
        extractor = ClaudeExtractor(raw_storage=temp_storage)
        assert extractor.source_name == "claude.ai"


def test_extract_all_stores_data(temp_storage, mock_claude_reader, fake_conversation_meta, fake_conversation_detail):
    """Test that extract_all stores conversation data in RawStorage."""
    # Setup mocks
    mock_claude_reader._fetch_conversation_list.return_value = [fake_conversation_meta]
    mock_claude_reader._extract_conversation_id.return_value = "conv-123"
    mock_claude_reader._fetch_conversation_detail.return_value = fake_conversation_detail
    
    with patch('src.extractors.claude.ClaudeReader', return_value=mock_claude_reader):
        extractor = ClaudeExtractor(raw_storage=temp_storage)
        stats = extractor.extract_all()
    
    # Verify data was stored
    stored = temp_storage.get_raw("claude.ai", "conv-123")
    assert stored is not None
    assert stored["source"] == "claude.ai"
    assert stored["source_id"] == "conv-123"
    assert stored["raw_data"] == fake_conversation_detail
    
    # Verify stats
    assert stats["extracted"] == 1
    assert stats["skipped"] == 0
    assert stats["errors"] == 0


def test_extract_all_returns_stats(temp_storage, mock_claude_reader, fake_conversation_meta, fake_conversation_detail):
    """Test that extract_all returns correct statistics."""
    # Setup mocks for multiple conversations
    conversations = [
        {"uuid": "conv-1", "name": "Chat 1"},
        {"uuid": "conv-2", "name": "Chat 2"},
        {"uuid": "conv-3", "name": "Chat 3"},
    ]
    
    mock_claude_reader._fetch_conversation_list.return_value = conversations
    
    def extract_id_side_effect(conv_meta):
        return conv_meta["uuid"]
    
    def fetch_detail_side_effect(conv_id):
        return {
            "uuid": conv_id,
            "name": f"Chat {conv_id[-1]}",
            "chat_messages": [],
        }
    
    mock_claude_reader._extract_conversation_id.side_effect = extract_id_side_effect
    mock_claude_reader._fetch_conversation_detail.side_effect = fetch_detail_side_effect
    
    with patch('src.extractors.claude.ClaudeReader', return_value=mock_claude_reader):
        extractor = ClaudeExtractor(raw_storage=temp_storage)
        stats = extractor.extract_all()
    
    # Verify stats structure and values
    assert isinstance(stats, dict)
    assert "extracted" in stats
    assert "skipped" in stats
    assert "errors" in stats
    assert stats["extracted"] == 3
    assert stats["skipped"] == 0
    assert stats["errors"] == 0
    
    # Verify all conversations were stored
    assert temp_storage.count("claude.ai") == 3


def test_extract_all_handles_missing_id(temp_storage, mock_claude_reader, fake_conversation_meta):
    """Test that extract_all handles conversations without ID correctly."""
    # Setup mock to return None for ID extraction
    mock_claude_reader._fetch_conversation_list.return_value = [fake_conversation_meta]
    mock_claude_reader._extract_conversation_id.return_value = None
    
    with patch('src.extractors.claude.ClaudeReader', return_value=mock_claude_reader):
        extractor = ClaudeExtractor(raw_storage=temp_storage)
        stats = extractor.extract_all()
    
    # Verify error was counted and nothing was stored
    assert stats["errors"] == 1
    assert stats["extracted"] == 0
    assert stats["skipped"] == 0
    assert temp_storage.count("claude.ai") == 0


def test_extract_one_found(temp_storage, mock_claude_reader, fake_conversation_detail):
    """Test extract_one when conversation is found."""
    # Setup mock to return conversation detail
    mock_claude_reader._fetch_conversation_detail.return_value = fake_conversation_detail
    
    with patch('src.extractors.claude.ClaudeReader', return_value=mock_claude_reader):
        extractor = ClaudeExtractor(raw_storage=temp_storage)
        result = extractor.extract_one("conv-123")
    
    # Verify result
    assert result is not None
    assert result == fake_conversation_detail
    
    # Verify data was stored
    stored = temp_storage.get_raw("claude.ai", "conv-123")
    assert stored is not None
    assert stored["raw_data"] == fake_conversation_detail


def test_extract_one_not_found(temp_storage, mock_claude_reader):
    """Test extract_one when conversation is not found."""
    # Setup mock to return None
    mock_claude_reader._fetch_conversation_detail.return_value = None
    
    with patch('src.extractors.claude.ClaudeReader', return_value=mock_claude_reader):
        extractor = ClaudeExtractor(raw_storage=temp_storage)
        result = extractor.extract_one("conv-nonexistent")
    
    # Verify result is None and nothing was stored
    assert result is None
    assert temp_storage.get_raw("claude.ai", "conv-nonexistent") is None


def test_deduplication(temp_storage, mock_claude_reader, fake_conversation_detail):
    """Test that extracting the same conversation twice results in deduplication."""
    # Setup mock to return same conversation detail
    mock_claude_reader._fetch_conversation_detail.return_value = fake_conversation_detail
    
    with patch('src.extractors.claude.ClaudeReader', return_value=mock_claude_reader):
        extractor = ClaudeExtractor(raw_storage=temp_storage)
        
        # Extract first time
        result1 = extractor.extract_one("conv-123")
        assert result1 is not None
        
        # Extract second time (should be deduplicated)
        result2 = extractor.extract_one("conv-123")
        assert result2 is not None
    
    # Verify only one record exists
    count = temp_storage.count("claude.ai")
    assert count == 1
    
    # Verify the stored data
    stored = temp_storage.get_raw("claude.ai", "conv-123")
    assert stored is not None
    assert stored["raw_data"] == fake_conversation_detail
