"""
Unit tests for ClaudeCodeExtractor.
"""
import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.extractors.claude_code import ClaudeCodeExtractor
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
    """Create a ClaudeCodeExtractor instance with temp storage."""
    with patch('src.extractors.claude_code.ClaudeCodeReader'):
        extractor = ClaudeCodeExtractor(temp_storage)
        extractor.reader = MagicMock()
        yield extractor


def test_source_name(extractor):
    """Test that source_name property returns 'claude-code'."""
    assert extractor.source_name == 'claude-code'


def test_extract_all_stores_data(extractor, temp_storage):
    """Test that extract_all stores session data in RawStorage."""
    # Mock read_all_sessions to return fake sessions
    fake_sessions = [
        {
            "session_id": "sess-123",
            "file_path": "/path/to/sess-123.jsonl",
            "summary": {"title": "Test Session 1"},
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ],
            "metadata": {"cwd": "/home/user", "git_branch": "main"},
            "project_path": "/Users/test/project",
            "project_encoded": "-Users-test-project"
        },
        {
            "session_id": "sess-456",
            "file_path": "/path/to/sess-456.jsonl",
            "summary": {"title": "Test Session 2"},
            "messages": [
                {"role": "user", "content": "How are you?"}
            ],
            "metadata": {"cwd": "/home/user", "git_branch": "feature"},
            "project_path": "/Users/test/project2",
            "project_encoded": "-Users-test-project2"
        }
    ]
    extractor.reader.read_all_sessions.return_value = iter(fake_sessions)
    
    # Extract all sessions
    stats = extractor.extract_all()
    
    # Verify stats
    assert stats['extracted'] == 2
    assert stats['skipped'] == 0
    assert stats['errors'] == 0
    
    # Verify data was stored in RawStorage
    stored1 = temp_storage.get_raw('claude-code', 'sess-123')
    assert stored1 is not None
    assert stored1['source_id'] == 'sess-123'
    assert stored1['raw_data']['session_id'] == 'sess-123'
    assert stored1['raw_data']['file_path'] == '/path/to/sess-123.jsonl'
    assert stored1['raw_data']['summary'] == {"title": "Test Session 1"}
    assert stored1['raw_data']['messages'] == fake_sessions[0]['messages']
    assert stored1['raw_data']['project_path'] == '/Users/test/project'
    
    stored2 = temp_storage.get_raw('claude-code', 'sess-456')
    assert stored2 is not None
    assert stored2['source_id'] == 'sess-456'
    assert stored2['raw_data']['session_id'] == 'sess-456'


def test_extract_all_returns_stats(extractor):
    """Test that extract_all returns correct statistics."""
    fake_sessions = [
        {
            "session_id": "sess-1",
            "file_path": "/path/to/sess-1.jsonl",
            "messages": [],
            "metadata": {},
            "project_path": "/project1",
            "project_encoded": "-project1"
        },
        {
            "session_id": "sess-2",
            "file_path": "/path/to/sess-2.jsonl",
            "messages": [],
            "metadata": {},
            "project_path": "/project2",
            "project_encoded": "-project2"
        },
        {
            "session_id": "sess-3",
            "file_path": "/path/to/sess-3.jsonl",
            "messages": [],
            "metadata": {},
            "project_path": "/project3",
            "project_encoded": "-project3"
        }
    ]
    extractor.reader.read_all_sessions.return_value = iter(fake_sessions)
    
    stats = extractor.extract_all()
    
    assert stats == {'extracted': 3, 'skipped': 0, 'errors': 0}


def test_extract_all_skips_no_id(extractor, temp_storage):
    """Test that sessions without session_id are skipped."""
    fake_sessions = [
        {
            "session_id": "sess-123",
            "file_path": "/path/to/sess-123.jsonl",
            "messages": [],
            "metadata": {},
            "project_path": "/project1",
            "project_encoded": "-project1"
        },
        {
            # Missing session_id
            "file_path": "/path/to/sess-456.jsonl",
            "messages": [],
            "metadata": {},
            "project_path": "/project2",
            "project_encoded": "-project2"
        },
        {
            "session_id": None,  # Explicitly None
            "file_path": "/path/to/sess-789.jsonl",
            "messages": [],
            "metadata": {},
            "project_path": "/project3",
            "project_encoded": "-project3"
        },
        {
            "session_id": "sess-999",
            "file_path": "/path/to/sess-999.jsonl",
            "messages": [],
            "metadata": {},
            "project_path": "/project4",
            "project_encoded": "-project4"
        }
    ]
    extractor.reader.read_all_sessions.return_value = iter(fake_sessions)
    
    stats = extractor.extract_all()
    
    # Should extract 2 (sess-123 and sess-999), skip 2 (no ID)
    assert stats['extracted'] == 2
    assert stats['skipped'] == 2
    assert stats['errors'] == 0
    
    # Verify only valid sessions were stored
    assert temp_storage.get_raw('claude-code', 'sess-123') is not None
    assert temp_storage.get_raw('claude-code', 'sess-999') is not None
    # Verify skipped sessions were not stored
    assert temp_storage.count('claude-code') == 2


def test_extract_one_found(extractor, temp_storage):
    """Test extract_one when session is found."""
    session_id = "sess-123"
    project_dir = Path("/path/to/project")
    session_file = project_dir / f"{session_id}.jsonl"
    
    fake_session = {
        "session_id": session_id,
        "file_path": str(session_file),
        "summary": {"title": "Test Session"},
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"}
        ],
        "metadata": {"cwd": "/home/user", "git_branch": "main"}
    }
    
    # Mock find_projects to return a project
    extractor.reader.find_projects.return_value = [
        {
            "dir_path": project_dir,
            "decoded_path": "/Users/test/project",
            "encoded_path": "-Users-test-project"
        }
    ]
    
    # Mock find_sessions to return the session file when called with project_dir
    def mock_find_sessions(project_path):
        if project_path == project_dir:
            return [session_file]
        return []
    extractor.reader.find_sessions.side_effect = mock_find_sessions
    
    # Mock read_session to return the session data
    extractor.reader.read_session.return_value = fake_session
    
    # Mock find_subagent_files to return empty list
    extractor.reader.find_subagent_files.return_value = []
    
    result = extractor.extract_one(session_id)
    
    # Verify result
    assert result is not None
    assert result['session_id'] == session_id
    assert result['file_path'] == str(session_file)
    assert result['messages'] == fake_session['messages']
    assert result['project_path'] == '/Users/test/project'
    
    # Verify stored in RawStorage
    stored = temp_storage.get_raw('claude-code', session_id)
    assert stored is not None
    assert stored['raw_data']['session_id'] == session_id
    assert stored['raw_data']['messages'] == fake_session['messages']


def test_extract_one_not_found(extractor, temp_storage):
    """Test extract_one when session is not found."""
    session_id = "non-existent-sess"
    
    # Mock find_projects to return projects
    extractor.reader.find_projects.return_value = [
        {
            "dir_path": Path("/path/to/project"),
            "decoded_path": "/Users/test/project",
            "encoded_path": "-Users-test-project"
        }
    ]
    
    # Mock find_sessions to return empty list (session not found)
    extractor.reader.find_sessions.return_value = []
    
    result = extractor.extract_one(session_id)
    
    # Should return None
    assert result is None
    
    # Should not be stored
    assert temp_storage.get_raw('claude-code', session_id) is None


def test_deduplication(extractor, temp_storage):
    """Test that extracting the same session twice only stores one record."""
    session_id = "sess-123"
    fake_session = {
        "session_id": session_id,
        "file_path": "/path/to/sess-123.jsonl",
        "summary": {"title": "Test Session"},
        "messages": [
            {"role": "user", "content": "Hello"}
        ],
        "metadata": {"cwd": "/home/user"},
        "project_path": "/Users/test/project",
        "project_encoded": "-Users-test-project"
    }
    
    # First extraction
    extractor.reader.read_all_sessions.return_value = iter([fake_session])
    stats1 = extractor.extract_all()
    assert stats1['extracted'] == 1
    
    # Second extraction with same data
    extractor.reader.read_all_sessions.return_value = iter([fake_session])
    stats2 = extractor.extract_all()
    assert stats2['extracted'] == 1
    
    # Verify only one record exists in storage
    count = temp_storage.count('claude-code')
    assert count == 1
    
    # Verify the stored record
    stored = temp_storage.get_raw('claude-code', session_id)
    assert stored is not None
    assert stored['raw_data']['session_id'] == session_id
