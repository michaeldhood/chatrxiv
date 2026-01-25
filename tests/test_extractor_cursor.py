"""
Unit tests for CursorExtractor.
"""
import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock

from src.extractors.cursor import CursorExtractor
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
def extractor(temp_storage):
    """Create a CursorExtractor instance with temp storage."""
    with patch('src.extractors.cursor.GlobalComposerReader'):
        extractor = CursorExtractor(temp_storage)
        extractor.global_reader = MagicMock()
        yield extractor


def test_source_name(extractor):
    """Test that source_name property returns 'cursor'."""
    assert extractor.source_name == 'cursor'


def test_extract_all_stores_data(extractor, temp_storage):
    """Test that extract_all stores composer data in RawStorage."""
    # Mock read_all_composers to return fake composers
    fake_composers = [
        {
            "composer_id": "uuid-123",
            "key": "composerData:uuid-123",
            "data": {"messages": [{"role": "user", "content": "test"}]}
        },
        {
            "composer_id": "uuid-456",
            "key": "composerData:uuid-456",
            "data": {"messages": [{"role": "assistant", "content": "response"}]}
        }
    ]
    extractor.global_reader.read_all_composers.return_value = iter(fake_composers)
    
    # Extract all composers
    stats = extractor.extract_all()
    
    # Verify stats
    assert stats['extracted'] == 2
    assert stats['skipped'] == 0
    assert stats['errors'] == 0
    
    # Verify data was stored in RawStorage
    stored1 = temp_storage.get_raw('cursor', 'uuid-123')
    assert stored1 is not None
    assert stored1['source_id'] == 'uuid-123'
    assert stored1['raw_data']['composer_id'] == 'uuid-123'
    assert stored1['raw_data']['key'] == 'composerData:uuid-123'
    assert stored1['raw_data']['data'] == fake_composers[0]['data']
    
    stored2 = temp_storage.get_raw('cursor', 'uuid-456')
    assert stored2 is not None
    assert stored2['source_id'] == 'uuid-456'
    assert stored2['raw_data']['composer_id'] == 'uuid-456'


def test_extract_all_returns_stats(extractor):
    """Test that extract_all returns correct statistics."""
    fake_composers = [
        {
            "composer_id": "uuid-1",
            "key": "composerData:uuid-1",
            "data": {"test": "data1"}
        },
        {
            "composer_id": "uuid-2",
            "key": "composerData:uuid-2",
            "data": {"test": "data2"}
        },
        {
            "composer_id": "uuid-3",
            "key": "composerData:uuid-3",
            "data": {"test": "data3"}
        }
    ]
    extractor.global_reader.read_all_composers.return_value = iter(fake_composers)
    
    stats = extractor.extract_all()
    
    assert stats == {'extracted': 3, 'skipped': 0, 'errors': 0}


def test_extract_all_skips_no_id(extractor, temp_storage):
    """Test that composers without composer_id are skipped."""
    fake_composers = [
        {
            "composer_id": "uuid-123",
            "key": "composerData:uuid-123",
            "data": {"test": "data"}
        },
        {
            # Missing composer_id
            "key": "composerData:uuid-456",
            "data": {"test": "data"}
        },
        {
            "composer_id": None,  # Explicitly None
            "key": "composerData:uuid-789",
            "data": {"test": "data"}
        },
        {
            "composer_id": "uuid-999",
            "key": "composerData:uuid-999",
            "data": {"test": "data"}
        }
    ]
    extractor.global_reader.read_all_composers.return_value = iter(fake_composers)
    
    stats = extractor.extract_all()
    
    # Should extract 2 (uuid-123 and uuid-999), skip 2 (no ID)
    assert stats['extracted'] == 2
    assert stats['skipped'] == 2
    assert stats['errors'] == 0
    
    # Verify only valid composers were stored
    assert temp_storage.get_raw('cursor', 'uuid-123') is not None
    assert temp_storage.get_raw('cursor', 'uuid-999') is not None
    assert temp_storage.get_raw('cursor', 'uuid-456') is None
    assert temp_storage.get_raw('cursor', 'uuid-789') is None


def test_extract_one_found(extractor, temp_storage):
    """Test extract_one when composer is found."""
    composer_id = "uuid-123"
    fake_composer = {
        "composer_id": composer_id,
        "data": {"messages": [{"role": "user", "content": "test"}]}
    }
    extractor.global_reader.read_composer.return_value = fake_composer
    
    result = extractor.extract_one(composer_id)
    
    # Verify result
    assert result is not None
    assert result['composer_id'] == composer_id
    assert result['data'] == fake_composer['data']
    
    # Verify stored in RawStorage
    stored = temp_storage.get_raw('cursor', composer_id)
    assert stored is not None
    assert stored['raw_data']['composer_id'] == composer_id
    assert stored['raw_data']['data'] == fake_composer['data']


def test_extract_one_not_found(extractor, temp_storage):
    """Test extract_one when composer is not found."""
    composer_id = "non-existent-uuid"
    extractor.global_reader.read_composer.return_value = None
    
    result = extractor.extract_one(composer_id)
    
    # Should return None
    assert result is None
    
    # Should not be stored
    assert temp_storage.get_raw('cursor', composer_id) is None


def test_deduplication(extractor, temp_storage):
    """Test that extracting the same composer twice only stores one record."""
    composer_id = "uuid-123"
    fake_composer = {
        "composer_id": composer_id,
        "key": "composerData:uuid-123",
        "data": {"messages": [{"role": "user", "content": "test"}]}
    }
    
    # First extraction
    extractor.global_reader.read_all_composers.return_value = iter([fake_composer])
    stats1 = extractor.extract_all()
    assert stats1['extracted'] == 1
    
    # Second extraction with same data
    extractor.global_reader.read_all_composers.return_value = iter([fake_composer])
    stats2 = extractor.extract_all()
    assert stats2['extracted'] == 1
    
    # Verify only one record exists in storage
    count = temp_storage.count('cursor')
    assert count == 1
    
    # Verify the stored record
    stored = temp_storage.get_raw('cursor', composer_id)
    assert stored is not None
    assert stored['raw_data']['composer_id'] == composer_id
