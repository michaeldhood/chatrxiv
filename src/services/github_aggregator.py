"""
GitHub activity aggregator service.

Orchestrates:
- Repository discovery (workspace → GitHub repo mapping)
- Activity ingestion (commits, PRs)
- Cross-referencing (linking chats to GitHub activity)
"""
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Set
from urllib.parse import unquote

from src.core.db import ChatDatabase
from src.core.models import (
    Repository, Commit, PullRequest, ChatActivityLink, ActivityLinkType
)
from src.readers.github_reader import GitHubReader

logger = logging.getLogger(__name__)


class GitHubAggregator:
    """
    Aggregates GitHub activity and links it to chats.
    
    Provides methods for:
    - Discovering repositories from workspaces
    - Ingesting commits and PRs
    - Cross-referencing chats with GitHub activity
    """
    
    def __init__(self, db: ChatDatabase):
        """
        Initialize aggregator.
        
        Parameters
        ----
        db : ChatDatabase
            Database instance
        """
        self.db = db
        self.github_reader = GitHubReader()
    
    # =================================================================
    # Repository Discovery
    # =================================================================
    
    def discover_repositories(
        self, 
        progress_callback: Optional[callable] = None
    ) -> Dict[str, int]:
        """
        Discover GitHub repositories from all workspaces.
        
        Scans workspace paths for .git directories and maps them to GitHub repos.
        
        Parameters
        ----
        progress_callback : callable, optional
            Callback(workspace_path, total, current) for progress
            
        Returns
        ----
        Dict[str, int]
            Stats: {"discovered": count, "skipped": count, "errors": count}
        """
        logger.info("Discovering GitHub repositories from workspaces...")
        
        stats = {"discovered": 0, "skipped": 0, "errors": 0, "updated": 0}
        
        # Get all workspaces with resolved paths
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT id, workspace_hash, resolved_path, folder_uri
            FROM workspaces
            WHERE resolved_path IS NOT NULL AND resolved_path != ''
        """)
        workspaces = cursor.fetchall()
        
        logger.info("Checking %d workspaces for GitHub repos...", len(workspaces))
        
        for idx, (ws_id, ws_hash, resolved_path, folder_uri) in enumerate(workspaces, 1):
            if progress_callback:
                progress_callback(resolved_path, len(workspaces), idx)
            
            # Normalize path
            path = resolved_path
            if path.startswith("file://"):
                path = unquote(path[7:])
            
            if not Path(path).exists():
                stats["skipped"] += 1
                continue
            
            try:
                # Try to discover repo
                repo = self.github_reader.discover_repository_from_path(path)
                if not repo:
                    stats["skipped"] += 1
                    continue
                
                # Check if already exists
                existing = self.db.get_repository_by_full_name(repo.full_name)
                
                # Link to workspace
                repo.workspace_id = ws_id
                
                # Get default branch from GitHub
                repo_info = self.github_reader.get_repo_info(repo.full_name)
                if repo_info:
                    repo.default_branch = repo_info.get("default_branch", "main")
                
                # Store in database
                self.db.upsert_repository(repo)
                
                if existing:
                    stats["updated"] += 1
                else:
                    stats["discovered"] += 1
                    logger.info("Discovered repository: %s at %s", 
                               repo.full_name, path)
                
            except Exception as e:
                logger.error("Error discovering repo at %s: %s", path, e)
                stats["errors"] += 1
        
        logger.info(
            "Repository discovery complete: %d discovered, %d updated, %d skipped, %d errors",
            stats["discovered"], stats["updated"], stats["skipped"], stats["errors"]
        )
        return stats
    
    def add_repository(
        self, 
        repo_identifier: str, 
        workspace_id: Optional[int] = None
    ) -> Optional[int]:
        """
        Add a repository by identifier (owner/repo).
        
        Parameters
        ----
        repo_identifier : str
            Repository identifier (e.g., "owner/repo")
        workspace_id : int, optional
            Workspace to link to
            
        Returns
        ----
        int, optional
            Repository ID or None on error
        """
        parsed = self.github_reader.parse_github_url(repo_identifier)
        if not parsed:
            logger.error("Invalid repository identifier: %s", repo_identifier)
            return None
        
        owner, name = parsed
        
        # Get repo info from GitHub
        repo_info = self.github_reader.get_repo_info(repo_identifier)
        if not repo_info:
            logger.error("Could not fetch repo info for: %s", repo_identifier)
            return None
        
        repo = Repository(
            owner=owner,
            name=name,
            full_name=f"{owner}/{name}",
            default_branch=repo_info.get("default_branch", "main"),
            workspace_id=workspace_id,
        )
        
        repo_id = self.db.upsert_repository(repo)
        logger.info("Added repository: %s (id=%d)", repo.full_name, repo_id)
        return repo_id
    
    # =================================================================
    # Activity Ingestion
    # =================================================================
    
    def ingest_commits(
        self, 
        repo_id: Optional[int] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        fetch_details: bool = True,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, int]:
        """
        Ingest commits from GitHub repositories.
        
        Parameters
        ----
        repo_id : int, optional
            Specific repository ID, or None for all repos
        since : datetime, optional
            Only commits after this date
        until : datetime, optional
            Only commits before this date
        limit : int
            Maximum commits per repository
        fetch_details : bool
            Whether to fetch file-level details for each commit
        progress_callback : callable, optional
            Progress callback
            
        Returns
        ----
        Dict[str, int]
            Stats: {"ingested": count, "skipped": count, "errors": count}
        """
        logger.info("Ingesting commits from GitHub...")
        
        stats = {"ingested": 0, "skipped": 0, "errors": 0}
        
        # Get repositories to process
        if repo_id:
            repos = [self.db.list_repositories()[0] for r in self.db.list_repositories() if r["id"] == repo_id]
        else:
            repos = self.db.list_repositories()
        
        if not repos:
            logger.warning("No repositories found to ingest commits from")
            return stats
        
        logger.info("Ingesting commits from %d repositories...", len(repos))
        
        for repo_data in repos:
            repo_full_name = repo_data["full_name"]
            repo_db_id = repo_data["id"]
            
            logger.info("Fetching commits from %s...", repo_full_name)
            
            try:
                commits = self.github_reader.get_commits(
                    repo_full_name,
                    since=since,
                    until=until,
                    branch=repo_data.get("default_branch"),
                    limit=limit
                )
                
                for idx, commit in enumerate(commits):
                    if progress_callback:
                        progress_callback(commit.sha[:7], len(commits), idx + 1)
                    
                    # Check if already exists
                    existing = self.db.get_commit_by_sha(repo_db_id, commit.sha)
                    if existing:
                        stats["skipped"] += 1
                        continue
                    
                    # Fetch details if requested
                    if fetch_details:
                        detailed = self.github_reader.get_commit_details(
                            repo_full_name, commit.sha
                        )
                        if detailed:
                            commit = detailed
                    
                    commit.repository_id = repo_db_id
                    self.db.upsert_commit(commit)
                    stats["ingested"] += 1
                
                # Update last synced
                cursor = self.db.conn.cursor()
                cursor.execute(
                    "UPDATE repositories SET last_synced_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), repo_db_id)
                )
                self.db.conn.commit()
                
            except Exception as e:
                logger.error("Error ingesting commits from %s: %s", repo_full_name, e)
                stats["errors"] += 1
        
        logger.info(
            "Commit ingestion complete: %d ingested, %d skipped, %d errors",
            stats["ingested"], stats["skipped"], stats["errors"]
        )
        return stats
    
    def ingest_pull_requests(
        self, 
        repo_id: Optional[int] = None,
        state: str = "all",
        limit: int = 100,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, int]:
        """
        Ingest pull requests from GitHub repositories.
        
        Parameters
        ----
        repo_id : int, optional
            Specific repository ID, or None for all repos
        state : str
            PR state: "open", "closed", "merged", "all"
        limit : int
            Maximum PRs per repository
        progress_callback : callable, optional
            Progress callback
            
        Returns
        ----
        Dict[str, int]
            Stats: {"ingested": count, "updated": count, "errors": count}
        """
        logger.info("Ingesting PRs from GitHub (state=%s)...", state)
        
        stats = {"ingested": 0, "updated": 0, "errors": 0}
        
        # Get repositories
        repos = self.db.list_repositories()
        if repo_id:
            repos = [r for r in repos if r["id"] == repo_id]
        
        if not repos:
            logger.warning("No repositories found to ingest PRs from")
            return stats
        
        logger.info("Ingesting PRs from %d repositories...", len(repos))
        
        for repo_data in repos:
            repo_full_name = repo_data["full_name"]
            repo_db_id = repo_data["id"]
            
            logger.info("Fetching PRs from %s...", repo_full_name)
            
            try:
                prs = self.github_reader.get_pull_requests(
                    repo_full_name,
                    state=state,
                    limit=limit
                )
                
                for idx, pr in enumerate(prs):
                    if progress_callback:
                        progress_callback(f"#{pr.number}", len(prs), idx + 1)
                    
                    # Check if already exists
                    existing = self.db.get_pull_request(repo_db_id, pr.number)
                    
                    pr.repository_id = repo_db_id
                    self.db.upsert_pull_request(pr)
                    
                    if existing:
                        stats["updated"] += 1
                    else:
                        stats["ingested"] += 1
                    
                    # Link PR commits if we have them
                    for sha in pr.commit_shas:
                        commit = self.db.get_commit_by_sha(repo_db_id, sha)
                        if commit:
                            self.db.link_pr_commit(
                                self.db.get_pull_request(repo_db_id, pr.number)["id"],
                                commit["id"]
                            )
                
            except Exception as e:
                logger.error("Error ingesting PRs from %s: %s", repo_full_name, e)
                stats["errors"] += 1
        
        logger.info(
            "PR ingestion complete: %d ingested, %d updated, %d errors",
            stats["ingested"], stats["updated"], stats["errors"]
        )
        return stats
    
    # =================================================================
    # Cross-Referencing
    # =================================================================
    
    def link_chat_to_activity(
        self, 
        chat_id: int,
        time_window_hours: int = 24,
        min_file_overlap: float = 0.1
    ) -> Dict[str, int]:
        """
        Find and create links between a chat and related GitHub activity.
        
        Uses multiple strategies:
        1. Temporal: Activity within time window of chat
        2. File overlap: Shared files between chat and commits
        
        Parameters
        ----
        chat_id : int
            Chat ID to link
        time_window_hours : int
            Hours before/after chat to consider for temporal linking
        min_file_overlap : float
            Minimum file overlap ratio (0-1) for file-based linking
            
        Returns
        ----
        Dict[str, int]
            Stats: {"commit_links": count, "pr_links": count}
        """
        stats = {"commit_links": 0, "pr_links": 0}
        
        # Get chat details
        chat = self.db.get_chat(chat_id)
        if not chat:
            logger.warning("Chat %d not found", chat_id)
            return stats
        
        workspace_id = chat.get("workspace_id")
        if not workspace_id:
            logger.debug("Chat %d has no workspace, skipping", chat_id)
            return stats
        
        # Get repository for workspace
        repo = self.db.get_repository_by_workspace(workspace_id)
        if not repo:
            logger.debug("No repository for workspace %d", workspace_id)
            return stats
        
        repo_id = repo["id"]
        
        # Parse chat timestamps
        chat_created = None
        chat_updated = None
        if chat.get("created_at"):
            try:
                chat_created = datetime.fromisoformat(chat["created_at"])
            except (ValueError, TypeError):
                pass
        if chat.get("last_updated_at"):
            try:
                chat_updated = datetime.fromisoformat(chat["last_updated_at"])
            except (ValueError, TypeError):
                pass
        
        if not chat_created:
            logger.debug("Chat %d has no timestamp", chat_id)
            return stats
        
        # Strategy 1: Temporal linking
        window = timedelta(hours=time_window_hours)
        start_time = chat_created - window
        end_time = (chat_updated or chat_created) + window
        
        # Find commits in time window
        commits = self.db.find_commits_in_range(repo_id, start_time, end_time)
        for commit in commits:
            link = ChatActivityLink(
                chat_id=chat_id,
                activity_type="commit",
                activity_id=commit["id"],
                link_type=ActivityLinkType.WORKSPACE_TEMPORAL,
                confidence=0.5,  # Medium confidence for temporal only
            )
            self.db.add_activity_link(link)
            stats["commit_links"] += 1
        
        # Find PRs in time window
        prs = self.db.find_prs_in_range(repo_id, start_time, end_time)
        for pr in prs:
            link = ChatActivityLink(
                chat_id=chat_id,
                activity_type="pr",
                activity_id=pr["id"],
                link_type=ActivityLinkType.WORKSPACE_TEMPORAL,
                confidence=0.5,
            )
            self.db.add_activity_link(link)
            stats["pr_links"] += 1
        
        # Strategy 2: File overlap
        chat_files = set(self._normalize_paths(chat.get("files", [])))
        if chat_files:
            # Find commits with file overlap
            file_commits = self.db.find_commits_by_files(
                repo_id, 
                list(chat_files)
            )
            for commit in file_commits:
                # Calculate overlap
                commit_files = set(f["path"] for f in self.db.get_commit_files(commit["id"]))
                overlap = len(chat_files & commit_files)
                confidence = overlap / max(len(chat_files), 1)
                
                if confidence >= min_file_overlap:
                    link = ChatActivityLink(
                        chat_id=chat_id,
                        activity_type="commit",
                        activity_id=commit["id"],
                        link_type=ActivityLinkType.FILE_OVERLAP,
                        confidence=min(confidence + 0.3, 1.0),  # Higher than temporal
                    )
                    self.db.add_activity_link(link)
                    # Don't double-count
                    if commit["id"] not in [c["id"] for c in commits]:
                        stats["commit_links"] += 1
        
        return stats
    
    def link_all_chats(
        self, 
        workspace_id: Optional[int] = None,
        time_window_hours: int = 24,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, int]:
        """
        Link all chats to GitHub activity.
        
        Parameters
        ----
        workspace_id : int, optional
            Limit to specific workspace
        time_window_hours : int
            Time window for temporal linking
        progress_callback : callable, optional
            Progress callback
            
        Returns
        ----
        Dict[str, int]
            Total stats across all chats
        """
        logger.info("Linking chats to GitHub activity...")
        
        total_stats = {"commit_links": 0, "pr_links": 0, "chats_processed": 0}
        
        # Get chats to process
        chats = self.db.list_chats(
            workspace_id=workspace_id, 
            limit=10000,
            empty_filter="non_empty"
        )
        
        logger.info("Processing %d chats...", len(chats))
        
        for idx, chat in enumerate(chats):
            if progress_callback:
                progress_callback(chat["title"] or "Untitled", len(chats), idx + 1)
            
            stats = self.link_chat_to_activity(
                chat["id"],
                time_window_hours=time_window_hours
            )
            
            total_stats["commit_links"] += stats["commit_links"]
            total_stats["pr_links"] += stats["pr_links"]
            total_stats["chats_processed"] += 1
        
        logger.info(
            "Linking complete: %d chats processed, %d commit links, %d PR links",
            total_stats["chats_processed"],
            total_stats["commit_links"],
            total_stats["pr_links"]
        )
        return total_stats
    
    def _normalize_paths(self, paths: List[str]) -> List[str]:
        """
        Normalize file paths for comparison.
        
        Strips workspace prefixes and normalizes separators.
        """
        normalized = []
        for p in paths:
            # Remove file:// prefix
            if p.startswith("file://"):
                p = unquote(p[7:])
            
            # Get relative path (from workspace root)
            # This is a heuristic - we take the last N path components
            parts = Path(p).parts
            if len(parts) > 3:
                # Skip common prefixes like /Users/foo/workspace/
                # Just keep the project-relative path
                p = str(Path(*parts[-3:]))
            
            normalized.append(p)
        
        return normalized
    
    # =================================================================
    # Query Methods
    # =================================================================
    
    def get_activity_timeline(
        self, 
        workspace_id: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get interleaved timeline of chats and GitHub activity for a workspace.
        
        Parameters
        ----
        workspace_id : int
            Workspace ID
        limit : int
            Maximum items
            
        Returns
        ----
        List[Dict[str, Any]]
            Timeline entries sorted by timestamp
        """
        cursor = self.db.conn.cursor()
        
        # Get repository for workspace
        repo = self.db.get_repository_by_workspace(workspace_id)
        
        timeline = []
        
        # Add chats
        chats = self.db.list_chats(workspace_id=workspace_id, limit=limit)
        for chat in chats:
            timeline.append({
                "type": "chat",
                "id": chat["id"],
                "title": chat["title"],
                "timestamp": chat["created_at"],
                "mode": chat["mode"],
                "messages_count": chat["messages_count"],
            })
        
        # Add commits if repo exists
        if repo:
            cursor.execute("""
                SELECT id, short_sha, message, author_login, authored_at,
                       additions, deletions
                FROM commits
                WHERE repository_id = ?
                ORDER BY authored_at DESC
                LIMIT ?
            """, (repo["id"], limit))
            
            for row in cursor.fetchall():
                timeline.append({
                    "type": "commit",
                    "id": row[0],
                    "title": row[2].split('\n')[0] if row[2] else "",
                    "timestamp": row[4],
                    "sha": row[1],
                    "author": row[3],
                    "additions": row[5],
                    "deletions": row[6],
                })
            
            # Add PRs
            cursor.execute("""
                SELECT id, number, title, state, author_login, created_at, merged_at
                FROM pull_requests
                WHERE repository_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (repo["id"], limit))
            
            for row in cursor.fetchall():
                timeline.append({
                    "type": "pr",
                    "id": row[0],
                    "title": row[2],
                    "timestamp": row[5],
                    "number": row[1],
                    "state": row[3],
                    "author": row[4],
                    "merged_at": row[6],
                })
        
        # Sort by timestamp
        def get_ts(item):
            ts = item.get("timestamp")
            if not ts:
                return ""
            return ts
        
        timeline.sort(key=get_ts, reverse=True)
        
        return timeline[:limit]
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics for GitHub integration.
        
        Returns
        ----
        Dict[str, Any]
            Summary stats
        """
        repos = self.db.list_repositories()
        link_counts = self.db.count_activity_links()
        
        return {
            "repositories": len(repos),
            "commits": self.db.count_commits(),
            "pull_requests": self.db.count_pull_requests(),
            "commit_links": link_counts.get("commit", 0),
            "pr_links": link_counts.get("pr", 0),
        }
