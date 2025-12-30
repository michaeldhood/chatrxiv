"""
Tests for GitHub activity integration.
"""
import pytest
import tempfile
import os
from datetime import datetime, timedelta

from src.core.db import ChatDatabase
from src.core.models import (
    Chat, Message, Workspace, ChatMode, MessageRole,
    Repository, Commit, CommitFile, PullRequest, PRState,
    ChatActivityLink, ActivityLinkType
)
from src.readers.github_reader import GitHubReader


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = ChatDatabase(path)
    yield db
    db.close()
    os.unlink(path)


class TestGitHubModels:
    """Tests for GitHub domain models."""
    
    def test_repository_full_name(self):
        """Test Repository auto-computes full_name."""
        repo = Repository(owner="anthropics", name="claude")
        assert repo.full_name == "anthropics/claude"
    
    def test_commit_short_sha(self):
        """Test Commit auto-computes short_sha."""
        commit = Commit(sha="abc123456789")
        assert commit.short_sha == "abc1234"
    
    def test_pr_state_enum(self):
        """Test PRState enum values."""
        assert PRState.OPEN.value == "open"
        assert PRState.MERGED.value == "merged"
        assert PRState.CLOSED.value == "closed"
    
    def test_activity_link_type_enum(self):
        """Test ActivityLinkType enum values."""
        assert ActivityLinkType.WORKSPACE_TEMPORAL.value == "workspace_temporal"
        assert ActivityLinkType.FILE_OVERLAP.value == "file_overlap"


class TestGitHubReader:
    """Tests for GitHubReader."""
    
    def test_parse_ssh_url(self):
        """Test parsing SSH git remote URL."""
        url = "git@github.com:anthropics/claude-code.git"
        result = GitHubReader.parse_github_url(url)
        assert result == ("anthropics", "claude-code")
    
    def test_parse_https_url(self):
        """Test parsing HTTPS git remote URL."""
        url = "https://github.com/anthropics/claude-code.git"
        result = GitHubReader.parse_github_url(url)
        assert result == ("anthropics", "claude-code")
    
    def test_parse_https_url_no_git_suffix(self):
        """Test parsing HTTPS URL without .git suffix."""
        url = "https://github.com/anthropics/claude-code"
        result = GitHubReader.parse_github_url(url)
        assert result == ("anthropics", "claude-code")
    
    def test_parse_plain_identifier(self):
        """Test parsing plain owner/repo format."""
        url = "anthropics/claude-code"
        result = GitHubReader.parse_github_url(url)
        assert result == ("anthropics", "claude-code")
    
    def test_parse_invalid_url(self):
        """Test parsing invalid URL returns None."""
        result = GitHubReader.parse_github_url("not-a-valid-url")
        assert result is None


class TestDatabaseGitHubTables:
    """Tests for GitHub-related database operations."""
    
    def test_repository_upsert(self, temp_db):
        """Test repository upsert functionality."""
        repo = Repository(
            owner="anthropics",
            name="claude",
            default_branch="main",
            remote_url="git@github.com:anthropics/claude.git",
        )
        
        repo_id = temp_db.upsert_repository(repo)
        assert repo_id is not None
        
        # Upsert again should return same ID (by owner/name)
        repo_id2 = temp_db.upsert_repository(repo)
        assert repo_id == repo_id2
    
    def test_repository_get_by_full_name(self, temp_db):
        """Test getting repository by full_name."""
        repo = Repository(
            owner="test",
            name="repo",
            default_branch="main",
        )
        temp_db.upsert_repository(repo)
        
        retrieved = temp_db.get_repository_by_full_name("test/repo")
        assert retrieved is not None
        assert retrieved["owner"] == "test"
        assert retrieved["name"] == "repo"
    
    def test_commit_upsert(self, temp_db):
        """Test commit upsert functionality."""
        # Create repo first
        repo = Repository(owner="test", name="repo")
        repo_id = temp_db.upsert_repository(repo)
        
        commit = Commit(
            repository_id=repo_id,
            sha="abc123456789",
            message="Test commit",
            author_name="Test Author",
            author_login="testuser",
            authored_at=datetime.now(),
            files=[
                CommitFile(path="src/test.py", status="modified", additions=10, deletions=5),
            ],
        )
        
        commit_id = temp_db.upsert_commit(commit)
        assert commit_id is not None
        
        # Verify commit was stored
        retrieved = temp_db.get_commit_by_sha(repo_id, "abc123456789")
        assert retrieved is not None
        assert retrieved["message"] == "Test commit"
        
        # Verify files were stored
        files = temp_db.get_commit_files(commit_id)
        assert len(files) == 1
        assert files[0]["path"] == "src/test.py"
    
    def test_find_commits_in_range(self, temp_db):
        """Test finding commits within a time range."""
        repo = Repository(owner="test", name="repo")
        repo_id = temp_db.upsert_repository(repo)
        
        now = datetime.now()
        
        # Create commits at different times
        for i, delta in enumerate([1, 3, 5, 7]):
            commit = Commit(
                repository_id=repo_id,
                sha=f"sha{i}",
                message=f"Commit {i}",
                authored_at=now - timedelta(days=delta),
            )
            temp_db.upsert_commit(commit)
        
        # Find commits in last 4 days
        start = now - timedelta(days=4)
        end = now
        
        found = temp_db.find_commits_in_range(repo_id, start, end)
        assert len(found) == 2  # delta=1 and delta=3
    
    def test_find_commits_by_files(self, temp_db):
        """Test finding commits by changed files."""
        repo = Repository(owner="test", name="repo")
        repo_id = temp_db.upsert_repository(repo)
        
        # Create commits with different files
        commit1 = Commit(
            repository_id=repo_id,
            sha="sha1",
            message="Update main.py",
            authored_at=datetime.now(),
            files=[CommitFile(path="src/main.py", status="modified")],
        )
        temp_db.upsert_commit(commit1)
        
        commit2 = Commit(
            repository_id=repo_id,
            sha="sha2",
            message="Update utils.py",
            authored_at=datetime.now(),
            files=[CommitFile(path="src/utils.py", status="modified")],
        )
        temp_db.upsert_commit(commit2)
        
        # Find commits that touched main.py
        found = temp_db.find_commits_by_files(repo_id, ["src/main.py"])
        assert len(found) == 1
        assert found[0]["message"] == "Update main.py"
    
    def test_pull_request_upsert(self, temp_db):
        """Test PR upsert functionality."""
        repo = Repository(owner="test", name="repo")
        repo_id = temp_db.upsert_repository(repo)
        
        pr = PullRequest(
            repository_id=repo_id,
            number=42,
            title="Add new feature",
            body="Description here",
            state=PRState.MERGED,
            author_login="testuser",
            head_branch="feature/new",
            base_branch="main",
            created_at=datetime.now(),
            merged_at=datetime.now(),
        )
        
        pr_id = temp_db.upsert_pull_request(pr)
        assert pr_id is not None
        
        # Verify PR was stored
        retrieved = temp_db.get_pull_request(repo_id, 42)
        assert retrieved is not None
        assert retrieved["title"] == "Add new feature"
        assert retrieved["state"] == "merged"
    
    def test_activity_link(self, temp_db):
        """Test chat-activity linking."""
        # Create workspace, chat, repo, and commit
        workspace = Workspace(workspace_hash="test123")
        workspace_id = temp_db.upsert_workspace(workspace)
        
        chat = Chat(
            cursor_composer_id="composer-123",
            workspace_id=workspace_id,
            title="Test Chat",
            messages=[Message(role=MessageRole.USER, text="test")],
        )
        chat_id = temp_db.upsert_chat(chat)
        
        repo = Repository(owner="test", name="repo", workspace_id=workspace_id)
        repo_id = temp_db.upsert_repository(repo)
        
        commit = Commit(
            repository_id=repo_id,
            sha="abc123",
            message="Test commit",
            authored_at=datetime.now(),
        )
        commit_id = temp_db.upsert_commit(commit)
        
        # Create link
        link = ChatActivityLink(
            chat_id=chat_id,
            activity_type="commit",
            activity_id=commit_id,
            link_type=ActivityLinkType.WORKSPACE_TEMPORAL,
            confidence=0.8,
        )
        link_id = temp_db.add_activity_link(link)
        assert link_id is not None
        
        # Verify link can be retrieved
        activity = temp_db.get_activity_for_chat(chat_id)
        assert len(activity) == 1
        assert activity[0]["activity_type"] == "commit"
        assert activity[0]["sha"] == "abc123"
    
    def test_get_chats_for_activity(self, temp_db):
        """Test finding chats linked to specific activity."""
        # Setup workspace, chat, repo, commit
        workspace = Workspace(workspace_hash="test123")
        workspace_id = temp_db.upsert_workspace(workspace)
        
        chat = Chat(
            cursor_composer_id="composer-123",
            workspace_id=workspace_id,
            title="Test Chat",
            messages=[Message(role=MessageRole.USER, text="test")],
        )
        chat_id = temp_db.upsert_chat(chat)
        
        repo = Repository(owner="test", name="repo")
        repo_id = temp_db.upsert_repository(repo)
        
        commit = Commit(
            repository_id=repo_id,
            sha="abc123",
            message="Test",
            authored_at=datetime.now(),
        )
        commit_id = temp_db.upsert_commit(commit)
        
        # Link chat to commit
        link = ChatActivityLink(
            chat_id=chat_id,
            activity_type="commit",
            activity_id=commit_id,
            link_type=ActivityLinkType.FILE_OVERLAP,
            confidence=0.9,
        )
        temp_db.add_activity_link(link)
        
        # Find chats for this commit
        chats = temp_db.get_chats_for_activity("commit", commit_id)
        assert len(chats) == 1
        assert chats[0]["title"] == "Test Chat"
        assert chats[0]["confidence"] == 0.9


class TestCrossReferencing:
    """Tests for cross-referencing logic."""
    
    def test_temporal_linking(self, temp_db):
        """Test that chats and commits within time window are linked."""
        from src.services.github_aggregator import GitHubAggregator
        
        # Create workspace with repo
        workspace = Workspace(
            workspace_hash="test123",
            resolved_path="/test/project"
        )
        workspace_id = temp_db.upsert_workspace(workspace)
        
        repo = Repository(
            owner="test",
            name="repo",
            workspace_id=workspace_id
        )
        repo_id = temp_db.upsert_repository(repo)
        
        now = datetime.now()
        
        # Create chat
        chat = Chat(
            cursor_composer_id="composer-123",
            workspace_id=workspace_id,
            title="Fixing bug",
            created_at=now,
            messages=[Message(role=MessageRole.USER, text="Fix the bug")],
        )
        chat_id = temp_db.upsert_chat(chat)
        
        # Create commit within time window (2 hours after chat)
        commit = Commit(
            repository_id=repo_id,
            sha="fix123",
            message="Fix bug",
            authored_at=now + timedelta(hours=2),
        )
        temp_db.upsert_commit(commit)
        
        # Run linking
        aggregator = GitHubAggregator(temp_db)
        stats = aggregator.link_chat_to_activity(chat_id, time_window_hours=24)
        
        assert stats["commit_links"] == 1
        
        # Verify link was created
        activity = temp_db.get_activity_for_chat(chat_id)
        assert len(activity) == 1
        assert activity[0]["message"] == "Fix bug"
