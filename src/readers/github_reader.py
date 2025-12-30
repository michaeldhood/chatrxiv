"""
Reader for GitHub activity using the gh CLI.

Fetches commits and pull requests from GitHub repositories.
Uses the gh CLI which is assumed to be authenticated.
"""
import json
import logging
import subprocess
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple

from src.core.models import Repository, Commit, CommitFile, PullRequest, PRState

logger = logging.getLogger(__name__)


class GitHubReader:
    """
    Reads GitHub activity using the gh CLI.
    
    Requires gh CLI to be installed and authenticated.
    """
    
    def __init__(self):
        """Initialize reader and verify gh is available."""
        self._verify_gh_cli()
    
    def _verify_gh_cli(self):
        """Verify gh CLI is installed and authenticated."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                logger.warning("gh CLI not authenticated: %s", result.stderr)
        except FileNotFoundError:
            raise RuntimeError("gh CLI not found. Please install: https://cli.github.com/")
        except subprocess.TimeoutExpired:
            raise RuntimeError("gh CLI timed out checking auth status")
    
    def _run_gh(self, args: List[str], timeout: int = 60) -> Optional[str]:
        """
        Run a gh command and return stdout.
        
        Parameters
        ----
        args : List[str]
            Arguments to pass to gh
        timeout : int
            Command timeout in seconds
            
        Returns
        ----
        str, optional
            Command output or None on error
        """
        cmd = ["gh"] + args
        logger.debug("Running: %s", " ".join(cmd))
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode != 0:
                logger.error("gh command failed: %s", result.stderr)
                return None
            return result.stdout
        except subprocess.TimeoutExpired:
            logger.error("gh command timed out: %s", " ".join(cmd))
            return None
        except Exception as e:
            logger.error("Error running gh: %s", e)
            return None
    
    @staticmethod
    def parse_github_url(url: str) -> Optional[Tuple[str, str]]:
        """
        Parse a GitHub URL or remote to extract owner/repo.
        
        Supports:
        - git@github.com:owner/repo.git
        - https://github.com/owner/repo.git
        - https://github.com/owner/repo
        - owner/repo
        
        Parameters
        ----
        url : str
            Git remote URL or repo identifier
            
        Returns
        ----
        Tuple[str, str], optional
            (owner, repo) or None if not parseable
        """
        # Handle SSH format: git@github.com:owner/repo.git
        ssh_match = re.match(r'git@github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', url)
        if ssh_match:
            return ssh_match.group(1), ssh_match.group(2)
        
        # Handle HTTPS format: https://github.com/owner/repo[.git]
        https_match = re.match(r'https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$', url)
        if https_match:
            return https_match.group(1), https_match.group(2)
        
        # Handle plain owner/repo format
        plain_match = re.match(r'^([^/]+)/([^/]+)$', url)
        if plain_match:
            return plain_match.group(1), plain_match.group(2)
        
        return None
    
    def discover_repository_from_path(self, path: str) -> Optional[Repository]:
        """
        Discover GitHub repository from a local git checkout.
        
        Reads .git/config to find the remote URL.
        
        Parameters
        ----
        path : str
            Path to local directory
            
        Returns
        ----
        Repository, optional
            Repository info or None if not a GitHub repo
        """
        git_dir = Path(path) / ".git"
        if not git_dir.exists():
            return None
        
        config_path = git_dir / "config"
        if not config_path.exists():
            return None
        
        try:
            with open(config_path, 'r') as f:
                config_content = f.read()
            
            # Find remote URL for origin
            # Look for: [remote "origin"] ... url = <url>
            remote_match = re.search(
                r'\[remote\s+"origin"\][^\[]*url\s*=\s*(\S+)',
                config_content,
                re.DOTALL
            )
            if not remote_match:
                # Try any remote if origin not found
                remote_match = re.search(
                    r'\[remote\s+"[^"]+"\][^\[]*url\s*=\s*(\S+)',
                    config_content,
                    re.DOTALL
                )
            
            if not remote_match:
                return None
            
            remote_url = remote_match.group(1)
            parsed = self.parse_github_url(remote_url)
            if not parsed:
                return None
            
            owner, name = parsed
            
            return Repository(
                owner=owner,
                name=name,
                full_name=f"{owner}/{name}",
                remote_url=remote_url,
                local_path=str(path),
            )
            
        except Exception as e:
            logger.debug("Error reading git config at %s: %s", config_path, e)
            return None
    
    def get_repo_info(self, repo: str) -> Optional[Dict[str, Any]]:
        """
        Get repository information from GitHub.
        
        Parameters
        ----
        repo : str
            Repository identifier (owner/repo)
            
        Returns
        ----
        Dict[str, Any], optional
            Repository info or None
        """
        output = self._run_gh([
            "repo", "view", repo,
            "--json", "name,owner,defaultBranchRef"
        ])
        if not output:
            return None
        
        try:
            data = json.loads(output)
            return {
                "name": data.get("name"),
                "owner": data.get("owner", {}).get("login"),
                "default_branch": data.get("defaultBranchRef", {}).get("name", "main"),
            }
        except json.JSONDecodeError as e:
            logger.error("Error parsing repo info: %s", e)
            return None
    
    def get_commits(
        self, 
        repo: str, 
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        branch: Optional[str] = None,
        limit: int = 100
    ) -> List[Commit]:
        """
        Fetch commits from a repository.
        
        Parameters
        ----
        repo : str
            Repository identifier (owner/repo)
        since : datetime, optional
            Only commits after this date
        until : datetime, optional
            Only commits before this date
        branch : str, optional
            Branch name (defaults to default branch)
        limit : int
            Maximum number of commits to fetch
            
        Returns
        ----
        List[Commit]
            List of commits
        """
        # Build API endpoint
        endpoint = f"repos/{repo}/commits"
        
        # Build query parameters
        params = ["-q", f".[:{ limit}]"]
        
        # Build jq query for transforming response
        jq_query = '.[] | {sha, message: .commit.message, author_name: .commit.author.name, author_email: .commit.author.email, author_login: .author.login, authored_at: .commit.author.date, committed_at: .commit.committer.date}'
        
        args = ["api", endpoint, "--paginate"]
        
        # Add query params
        if since:
            args.extend(["-f", f"since={since.isoformat()}Z"])
        if until:
            args.extend(["-f", f"until={until.isoformat()}Z"])
        if branch:
            args.extend(["-f", f"sha={branch}"])
        
        args.extend(["-f", f"per_page={min(limit, 100)}"])
        
        output = self._run_gh(args, timeout=120)
        if not output:
            return []
        
        try:
            data = json.loads(output)
            if not isinstance(data, list):
                data = [data]
            
            commits = []
            for item in data[:limit]:
                commit = Commit(
                    sha=item.get("sha", ""),
                    message=item.get("commit", {}).get("message", ""),
                    author_name=item.get("commit", {}).get("author", {}).get("name", ""),
                    author_email=item.get("commit", {}).get("author", {}).get("email", ""),
                    author_login=item.get("author", {}).get("login", "") if item.get("author") else "",
                    authored_at=self._parse_timestamp(
                        item.get("commit", {}).get("author", {}).get("date")
                    ),
                    committed_at=self._parse_timestamp(
                        item.get("commit", {}).get("committer", {}).get("date")
                    ),
                    branch=branch,
                )
                commits.append(commit)
            
            return commits
            
        except json.JSONDecodeError as e:
            logger.error("Error parsing commits: %s", e)
            return []
    
    def get_commit_details(self, repo: str, sha: str) -> Optional[Commit]:
        """
        Get detailed commit information including files changed.
        
        Parameters
        ----
        repo : str
            Repository identifier (owner/repo)
        sha : str
            Commit SHA
            
        Returns
        ----
        Commit, optional
            Commit with files or None
        """
        output = self._run_gh([
            "api", f"repos/{repo}/commits/{sha}"
        ])
        if not output:
            return None
        
        try:
            data = json.loads(output)
            
            files = []
            for f in data.get("files", []):
                files.append(CommitFile(
                    path=f.get("filename", ""),
                    status=f.get("status", ""),
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                ))
            
            commit = Commit(
                sha=data.get("sha", ""),
                message=data.get("commit", {}).get("message", ""),
                author_name=data.get("commit", {}).get("author", {}).get("name", ""),
                author_email=data.get("commit", {}).get("author", {}).get("email", ""),
                author_login=data.get("author", {}).get("login", "") if data.get("author") else "",
                authored_at=self._parse_timestamp(
                    data.get("commit", {}).get("author", {}).get("date")
                ),
                committed_at=self._parse_timestamp(
                    data.get("commit", {}).get("committer", {}).get("date")
                ),
                additions=data.get("stats", {}).get("additions", 0),
                deletions=data.get("stats", {}).get("deletions", 0),
                files_changed=len(files),
                files=files,
            )
            return commit
            
        except json.JSONDecodeError as e:
            logger.error("Error parsing commit details: %s", e)
            return None
    
    def get_pull_requests(
        self, 
        repo: str, 
        state: str = "all",
        limit: int = 100
    ) -> List[PullRequest]:
        """
        Fetch pull requests from a repository.
        
        Parameters
        ----
        repo : str
            Repository identifier (owner/repo)
        state : str
            PR state filter: "open", "closed", "merged", "all"
        limit : int
            Maximum number of PRs to fetch
            
        Returns
        ----
        List[PullRequest]
            List of pull requests
        """
        # Use gh pr list command for better formatting
        args = [
            "pr", "list",
            "--repo", repo,
            "--state", state if state != "merged" else "closed",
            "--limit", str(limit),
            "--json", "number,title,body,state,author,headRefName,baseRefName,createdAt,updatedAt,mergedAt,closedAt,additions,deletions,changedFiles,commits"
        ]
        
        output = self._run_gh(args, timeout=120)
        if not output:
            return []
        
        try:
            data = json.loads(output)
            
            prs = []
            for item in data:
                # Determine state
                pr_state = PRState.OPEN
                if item.get("mergedAt"):
                    pr_state = PRState.MERGED
                elif item.get("state") == "CLOSED":
                    pr_state = PRState.CLOSED
                
                # Filter for merged if requested
                if state == "merged" and pr_state != PRState.MERGED:
                    continue
                
                pr = PullRequest(
                    number=item.get("number", 0),
                    title=item.get("title", ""),
                    body=item.get("body", ""),
                    state=pr_state,
                    author_login=item.get("author", {}).get("login", "") if item.get("author") else "",
                    head_branch=item.get("headRefName", ""),
                    base_branch=item.get("baseRefName", ""),
                    created_at=self._parse_timestamp(item.get("createdAt")),
                    updated_at=self._parse_timestamp(item.get("updatedAt")),
                    merged_at=self._parse_timestamp(item.get("mergedAt")),
                    closed_at=self._parse_timestamp(item.get("closedAt")),
                    additions=item.get("additions", 0),
                    deletions=item.get("deletions", 0),
                    changed_files=item.get("changedFiles", 0),
                    commits_count=len(item.get("commits", [])),
                    commit_shas=[c.get("oid", "") for c in item.get("commits", [])],
                )
                prs.append(pr)
            
            return prs
            
        except json.JSONDecodeError as e:
            logger.error("Error parsing PRs: %s", e)
            return []
    
    def get_pr_details(self, repo: str, number: int) -> Optional[PullRequest]:
        """
        Get detailed PR information.
        
        Parameters
        ----
        repo : str
            Repository identifier (owner/repo)
        number : int
            PR number
            
        Returns
        ----
        PullRequest, optional
            PR with details or None
        """
        output = self._run_gh([
            "pr", "view", str(number),
            "--repo", repo,
            "--json", "number,title,body,state,author,headRefName,baseRefName,createdAt,updatedAt,mergedAt,closedAt,additions,deletions,changedFiles,commits"
        ])
        if not output:
            return None
        
        try:
            item = json.loads(output)
            
            pr_state = PRState.OPEN
            if item.get("mergedAt"):
                pr_state = PRState.MERGED
            elif item.get("state") == "CLOSED":
                pr_state = PRState.CLOSED
            
            return PullRequest(
                number=item.get("number", 0),
                title=item.get("title", ""),
                body=item.get("body", ""),
                state=pr_state,
                author_login=item.get("author", {}).get("login", "") if item.get("author") else "",
                head_branch=item.get("headRefName", ""),
                base_branch=item.get("baseRefName", ""),
                created_at=self._parse_timestamp(item.get("createdAt")),
                updated_at=self._parse_timestamp(item.get("updatedAt")),
                merged_at=self._parse_timestamp(item.get("mergedAt")),
                closed_at=self._parse_timestamp(item.get("closedAt")),
                additions=item.get("additions", 0),
                deletions=item.get("deletions", 0),
                changed_files=item.get("changedFiles", 0),
                commits_count=len(item.get("commits", [])),
                commit_shas=[c.get("oid", "") for c in item.get("commits", [])],
            )
            
        except json.JSONDecodeError as e:
            logger.error("Error parsing PR details: %s", e)
            return None
    
    def get_pr_commits(self, repo: str, number: int) -> List[str]:
        """
        Get commit SHAs for a PR.
        
        Parameters
        ----
        repo : str
            Repository identifier (owner/repo)
        number : int
            PR number
            
        Returns
        ----
        List[str]
            List of commit SHAs
        """
        output = self._run_gh([
            "api", f"repos/{repo}/pulls/{number}/commits",
            "--paginate"
        ])
        if not output:
            return []
        
        try:
            data = json.loads(output)
            if not isinstance(data, list):
                data = [data]
            return [c.get("sha", "") for c in data if c.get("sha")]
        except json.JSONDecodeError:
            return []
    
    def _parse_timestamp(self, ts: Optional[str]) -> Optional[datetime]:
        """Parse ISO timestamp to datetime."""
        if not ts:
            return None
        try:
            # Handle Z suffix
            if ts.endswith('Z'):
                ts = ts[:-1] + '+00:00'
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return None
