"""
Tests for RawStorage class.
"""
import pytest
import tempfile
import os
from datetime import datetime, timedelta

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


def test_store_raw_basic(temp_storage):
    """Test storing raw data returns an ID."""
    raw_data = {"foo": "bar", "nested": {"key": "value"}}
    row_id = temp_storage.store_raw("cursor", "composer-123", raw_data)
    assert row_id is not None
    assert isinstance(row_id, int)
    assert row_id > 0


def test_get_raw_retrieves_stored(temp_storage):
    """Test retrieving stored raw data."""
    raw_data = {"foo": "bar", "nested": {"key": "value"}}
    source = "cursor"
    source_id = "composer-123"
    
    row_id = temp_storage.store_raw(source, source_id, raw_data)
    
    retrieved = temp_storage.get_raw(source, source_id)
    assert retrieved is not None
    assert retrieved["id"] == row_id
    assert retrieved["source"] == source
    assert retrieved["source_id"] == source_id
    assert retrieved["raw_data"] == raw_data  # Should be parsed JSON dict, not string
    assert isinstance(retrieved["raw_data"], dict)
    assert retrieved["checksum"] is not None


def test_deduplication_same_data(temp_storage):
    """Test that storing identical data twice returns same ID."""
    raw_data = {"foo": "bar", "nested": {"key": "value"}}
    source = "claude.ai"
    source_id = "conv-456"
    
    row_id1 = temp_storage.store_raw(source, source_id, raw_data)
    row_id2 = temp_storage.store_raw(source, source_id, raw_data)
    
    assert row_id1 == row_id2
    
    # Verify only one record exists
    count = temp_storage.count(source)
    assert count == 1


def test_deduplication_different_data(temp_storage):
    """Test that storing different data for same source_id creates new record."""
    source = "chatgpt"
    source_id = "session-789"
    
    raw_data1 = {"message": "first"}
    raw_data2 = {"message": "second"}
    
    row_id1 = temp_storage.store_raw(source, source_id, raw_data1)
    row_id2 = temp_storage.store_raw(source, source_id, raw_data2)
    
    assert row_id1 != row_id2
    
    # Verify both records exist
    count = temp_storage.count(source)
    assert count == 2
    
    # Verify latest is returned
    retrieved = temp_storage.get_raw(source, source_id)
    assert retrieved["raw_data"] == raw_data2


def test_get_all_raw_iterates(temp_storage):
    """Test iterating over all raw data for a source."""
    source = "claude-code"
    source_id1 = "code-1"
    source_id2 = "code-2"
    
    raw_data1 = {"file": "test1.py", "content": "print('hello')"}
    raw_data2 = {"file": "test2.py", "content": "print('world')"}
    
    temp_storage.store_raw(source, source_id1, raw_data1)
    temp_storage.store_raw(source, source_id2, raw_data2)
    
    results = list(temp_storage.get_all_raw(source))
    assert len(results) == 2
    
    # Verify all results have correct structure
    for result in results:
        assert "id" in result
        assert "source" in result
        assert "source_id" in result
        assert "extracted_at" in result
        assert "raw_data" in result
        assert "checksum" in result
        assert isinstance(result["raw_data"], dict)
        assert result["source"] == source
    
    # Verify we got both source_ids
    source_ids = {r["source_id"] for r in results}
    assert source_ids == {source_id1, source_id2}


def test_get_all_raw_since_filter(temp_storage):
    """Test filtering by timestamp."""
    source = "cursor"
    
    # Store first record
    raw_data1 = {"first": "record"}
    extracted_at1 = datetime.utcnow() - timedelta(hours=2)
    temp_storage.store_raw(source, "id-1", raw_data1, extracted_at1)
    
    # Store second record
    raw_data2 = {"second": "record"}
    extracted_at2 = datetime.utcnow() - timedelta(hours=1)
    temp_storage.store_raw(source, "id-2", raw_data2, extracted_at2)
    
    # Store third record
    raw_data3 = {"third": "record"}
    extracted_at3 = datetime.utcnow()
    temp_storage.store_raw(source, "id-3", raw_data3, extracted_at3)
    
    # Filter to get only records after extracted_at2
    since = extracted_at2 + timedelta(minutes=30)
    results = list(temp_storage.get_all_raw(source, since=since))
    
    # Should only get the third record
    assert len(results) == 1
    assert results[0]["source_id"] == "id-3"
    assert results[0]["raw_data"] == raw_data3


def test_count_all(temp_storage):
    """Test counting all records."""
    # Store records from different sources
    temp_storage.store_raw("cursor", "id-1", {"data": 1})
    temp_storage.store_raw("claude.ai", "id-2", {"data": 2})
    temp_storage.store_raw("chatgpt", "id-3", {"data": 3})
    temp_storage.store_raw("claude-code", "id-4", {"data": 4})
    
    total_count = temp_storage.count()
    assert total_count == 4


def test_count_by_source(temp_storage):
    """Test counting records filtered by source."""
    # Store multiple records for cursor
    temp_storage.store_raw("cursor", "id-1", {"data": 1})
    temp_storage.store_raw("cursor", "id-2", {"data": 2})
    temp_storage.store_raw("cursor", "id-3", {"data": 3})
    
    # Store records for other sources
    temp_storage.store_raw("claude.ai", "id-4", {"data": 4})
    temp_storage.store_raw("chatgpt", "id-5", {"data": 5})
    
    cursor_count = temp_storage.count("cursor")
    assert cursor_count == 3
    
    claude_count = temp_storage.count("claude.ai")
    assert claude_count == 1
    
    chatgpt_count = temp_storage.count("chatgpt")
    assert chatgpt_count == 1


def test_get_sources(temp_storage):
    """Test getting distinct sources."""
    # Store records from different sources
    temp_storage.store_raw("cursor", "id-1", {"data": 1})
    temp_storage.store_raw("claude.ai", "id-2", {"data": 2})
    temp_storage.store_raw("chatgpt", "id-3", {"data": 3})
    temp_storage.store_raw("claude-code", "id-4", {"data": 4})
    
    sources = temp_storage.get_sources()
    assert len(sources) == 4
    assert "cursor" in sources
    assert "claude.ai" in sources
    assert "chatgpt" in sources
    assert "claude-code" in sources
    
    # Should be sorted
    assert sources == sorted(sources)


def test_get_raw_not_found(temp_storage):
    """Test that get_raw returns None for non-existent item."""
    result = temp_storage.get_raw("cursor", "non-existent-id")
    assert result is None


def test_context_manager(temp_storage):
    """Test context manager usage."""
    # Use context manager
    with RawStorage(temp_storage.db_path) as storage:
        raw_data = {"test": "context_manager"}
        row_id = storage.store_raw("cursor", "ctx-1", raw_data)
        assert row_id is not None
        
        retrieved = storage.get_raw("cursor", "ctx-1")
        assert retrieved is not None
        assert retrieved["raw_data"] == raw_data
    
    # After context exit, connection should be closed
    # Try to use the original temp_storage (should still work)
    retrieved = temp_storage.get_raw("cursor", "ctx-1")
    assert retrieved is not None


def test_store_raw_with_custom_timestamp(temp_storage):
    """Test storing with custom extracted_at timestamp."""
    custom_time = datetime.utcnow() - timedelta(days=1)
    raw_data = {"custom": "timestamp"}
    
    row_id = temp_storage.store_raw("cursor", "custom-time", raw_data, extracted_at=custom_time)
    
    retrieved = temp_storage.get_raw("cursor", "custom-time")
    assert retrieved is not None
    # Verify timestamp is stored correctly (as ISO string)
    assert retrieved["extracted_at"] == custom_time.isoformat()


def test_get_all_raw_ordering(temp_storage):
    """Test that get_all_raw returns records in chronological order."""
    source = "cursor"
    base_time = datetime.utcnow() - timedelta(hours=3)
    
    # Store records with different timestamps
    temp_storage.store_raw(source, "id-1", {"order": 1}, extracted_at=base_time)
    temp_storage.store_raw(source, "id-2", {"order": 2}, extracted_at=base_time + timedelta(hours=1))
    temp_storage.store_raw(source, "id-3", {"order": 3}, extracted_at=base_time + timedelta(hours=2))
    
    results = list(temp_storage.get_all_raw(source))
    assert len(results) == 3
    
    # Should be ordered by extracted_at ASC
    extracted_times = [r["extracted_at"] for r in results]
    assert extracted_times == sorted(extracted_times)


def test_checksum_consistency(temp_storage):
    """Test that checksums are consistent for same data."""
    raw_data = {"consistent": "data"}
    source = "cursor"
    source_id = "checksum-test"
    
    row_id1 = temp_storage.store_raw(source, source_id, raw_data)
    retrieved1 = temp_storage.get_raw(source, source_id)
    checksum1 = retrieved1["checksum"]
    
    # Store same data again
    row_id2 = temp_storage.store_raw(source, source_id, raw_data)
    retrieved2 = temp_storage.get_raw(source, source_id)
    checksum2 = retrieved2["checksum"]
    
    assert checksum1 == checksum2
    assert row_id1 == row_id2
