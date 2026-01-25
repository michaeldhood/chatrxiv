"""
Unit tests for ChatGPTExtractor.
"""
import pytest
import tempfile
import os
import json
import zipfile
from pathlib import Path

from src.extractors.chatgpt import ChatGPTExtractor
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
def temp_json_file():
    """Create a temporary conversations.json file."""
    conversations = [
        {
            "id": "conv-1",
            "title": "Test Conversation 1",
            "mapping": {"message-1": {"id": "message-1"}},
            "create_time": 1234567890.0
        },
        {
            "id": "conv-2",
            "title": "Test Conversation 2",
            "mapping": {"message-2": {"id": "message-2"}},
            "create_time": 1234567891.0
        },
        {
            "conversation_id": "conv-3",
            "title": "Test Conversation 3",
            "mapping": {"message-3": {"id": "message-3"}},
            "create_time": 1234567892.0
        }
    ]
    
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(conversations, f)
    
    yield Path(path)
    os.unlink(path)


@pytest.fixture
def temp_zip_file():
    """Create a temporary ZIP file containing conversations.json."""
    conversations = [
        {
            "id": "conv-zip-1",
            "title": "ZIP Conversation 1",
            "mapping": {"message-1": {"id": "message-1"}},
            "create_time": 1234567890.0
        },
        {
            "id": "conv-zip-2",
            "title": "ZIP Conversation 2",
            "mapping": {"message-2": {"id": "message-2"}},
            "create_time": 1234567891.0
        }
    ]
    
    fd, path = tempfile.mkstemp(suffix='.zip')
    os.close(fd)
    
    with zipfile.ZipFile(path, 'w') as zip_ref:
        zip_ref.writestr('conversations.json', json.dumps(conversations))
    
    yield Path(path)
    os.unlink(path)


def test_source_name(temp_storage):
    """Test that source_name property returns 'chatgpt'."""
    extractor = ChatGPTExtractor(temp_storage, export_path=Path('/tmp/test.json'))
    assert extractor.source_name == 'chatgpt'


def test_extract_all_from_json(temp_storage, temp_json_file):
    """Test extracting all conversations from a JSON file."""
    extractor = ChatGPTExtractor(temp_storage, export_path=temp_json_file)
    
    stats = extractor.extract_all()
    
    # Verify stats
    assert stats['extracted'] == 3
    assert stats['skipped'] == 0
    assert stats['errors'] == 0
    
    # Verify data was stored in RawStorage
    stored1 = temp_storage.get_raw('chatgpt', 'conv-1')
    assert stored1 is not None
    assert stored1['source_id'] == 'conv-1'
    assert stored1['raw_data']['id'] == 'conv-1'
    assert stored1['raw_data']['title'] == 'Test Conversation 1'
    
    stored2 = temp_storage.get_raw('chatgpt', 'conv-2')
    assert stored2 is not None
    assert stored2['source_id'] == 'conv-2'
    
    stored3 = temp_storage.get_raw('chatgpt', 'conv-3')
    assert stored3 is not None
    assert stored3['source_id'] == 'conv-3'
    assert stored3['raw_data']['conversation_id'] == 'conv-3'


def test_extract_all_from_zip(temp_storage, temp_zip_file):
    """Test extracting all conversations from a ZIP file."""
    extractor = ChatGPTExtractor(temp_storage, export_path=temp_zip_file)
    
    stats = extractor.extract_all()
    
    # Verify stats
    assert stats['extracted'] == 2
    assert stats['skipped'] == 0
    assert stats['errors'] == 0
    
    # Verify data was stored in RawStorage
    stored1 = temp_storage.get_raw('chatgpt', 'conv-zip-1')
    assert stored1 is not None
    assert stored1['source_id'] == 'conv-zip-1'
    assert stored1['raw_data']['id'] == 'conv-zip-1'
    assert stored1['raw_data']['title'] == 'ZIP Conversation 1'
    
    stored2 = temp_storage.get_raw('chatgpt', 'conv-zip-2')
    assert stored2 is not None
    assert stored2['source_id'] == 'conv-zip-2'


def test_extract_all_returns_stats(temp_storage, temp_json_file):
    """Test that extract_all returns correct statistics."""
    extractor = ChatGPTExtractor(temp_storage, export_path=temp_json_file)
    
    stats = extractor.extract_all()
    
    assert isinstance(stats, dict)
    assert 'extracted' in stats
    assert 'skipped' in stats
    assert 'errors' in stats
    assert stats['extracted'] == 3
    assert stats['skipped'] == 0
    assert stats['errors'] == 0


def test_extract_all_skips_no_id(temp_storage):
    """Test that conversations without id are skipped."""
    conversations = [
        {
            "id": "conv-1",
            "title": "Valid Conversation",
            "mapping": {}
        },
        {
            # Missing id
            "title": "No ID Conversation",
            "mapping": {}
        },
        {
            "id": None,  # Explicitly None
            "title": "None ID Conversation",
            "mapping": {}
        },
        {
            "conversation_id": "conv-4",
            "title": "Valid with conversation_id",
            "mapping": {}
        }
    ]
    
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(conversations, f)
    
    try:
        extractor = ChatGPTExtractor(temp_storage, export_path=Path(path))
        
        stats = extractor.extract_all()
        
        # Should extract 2 (conv-1 and conv-4), skip 2 (no ID)
        assert stats['extracted'] == 2
        assert stats['skipped'] == 2
        assert stats['errors'] == 0
        
        # Verify only valid conversations were stored
        assert temp_storage.get_raw('chatgpt', 'conv-1') is not None
        assert temp_storage.get_raw('chatgpt', 'conv-4') is not None
    finally:
        os.unlink(path)


def test_extract_one_found(temp_storage, temp_json_file):
    """Test extract_one when conversation is found."""
    extractor = ChatGPTExtractor(temp_storage, export_path=temp_json_file)
    
    result = extractor.extract_one('conv-1')
    
    # Verify result
    assert result is not None
    assert result['id'] == 'conv-1'
    assert result['title'] == 'Test Conversation 1'
    
    # Verify stored in RawStorage
    stored = temp_storage.get_raw('chatgpt', 'conv-1')
    assert stored is not None
    assert stored['raw_data']['id'] == 'conv-1'
    assert stored['raw_data']['title'] == 'Test Conversation 1'


def test_extract_one_not_found(temp_storage, temp_json_file):
    """Test extract_one when conversation is not found."""
    extractor = ChatGPTExtractor(temp_storage, export_path=temp_json_file)
    
    result = extractor.extract_one('non-existent-id')
    
    # Should return None
    assert result is None
    
    # Should not be stored
    assert temp_storage.get_raw('chatgpt', 'non-existent-id') is None


def test_no_export_path_raises(temp_storage):
    """Test that ValueError is raised when export_path is not set."""
    extractor = ChatGPTExtractor(temp_storage, export_path=None)
    
    # Test that _load_conversations raises ValueError
    with pytest.raises(ValueError, match="export_path not set"):
        extractor._load_conversations()
    
    # Also verify that extract_all handles it gracefully by returning errors
    stats = extractor.extract_all()
    assert stats['errors'] == 1
    assert stats['extracted'] == 0


def test_invalid_json_raises(temp_storage):
    """Test that ValueError is raised for malformed JSON."""
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('{"invalid": json}')  # Invalid JSON
    
    try:
        extractor = ChatGPTExtractor(temp_storage, export_path=Path(path))
        
        # Test that _load_conversations raises ValueError
        with pytest.raises(ValueError, match="Invalid JSON"):
            extractor._load_conversations()
        
        # Also verify that extract_all handles it gracefully by returning errors
        stats = extractor.extract_all()
        assert stats['errors'] == 1
        assert stats['extracted'] == 0
    finally:
        os.unlink(path)
