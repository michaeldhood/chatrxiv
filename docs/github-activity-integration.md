# GitHub Activity Integration Design

## Overview

This document describes the design for integrating GitHub activity (commits and pull requests) into the Cursor Chat Extractor, and how to cross-reference this activity with chat conversations.

## Goals

1. **Ingest GitHub Activity**: Pull commits and PRs from GitHub repositories linked to workspaces
2. **Cross-Reference**: Link chats to related commits/PRs via multiple strategies
3. **Query Interface**: Enable searching and viewing activity alongside chats

## Data Model

### New Tables

#### `repositories`

Maps workspaces to GitHub repositories.

```sql
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER,
    owner TEXT NOT NULL,           -- e.g., "anthropics"
    name TEXT NOT NULL,            -- e.g., "claude-code"
    full_name TEXT NOT NULL,       -- e.g., "anthropics/claude-code"
    default_branch TEXT,           -- e.g., "main"
    remote_url TEXT,               -- git@github.com:... or https://...
    local_path TEXT,               -- resolved local path
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TEXT,
    UNIQUE(owner, name),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
```

#### `commits`

Stores commit metadata.

```sql
CREATE TABLE IF NOT EXISTS commits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL,
    sha TEXT NOT NULL,
    short_sha TEXT NOT NULL,       -- first 7 chars
    message TEXT,
    author_name TEXT,
    author_email TEXT,
    author_login TEXT,             -- GitHub username
    authored_at TEXT NOT NULL,     -- when written
    committed_at TEXT,             -- when committed
    branch TEXT,                   -- branch name if known
    additions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    files_changed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(repository_id, sha),
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
);
```

#### `commit_files`

Files changed in each commit (for cross-referencing with chat_files).

```sql
CREATE TABLE IF NOT EXISTS commit_files (
    commit_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    status TEXT,                   -- added, modified, deleted, renamed
    additions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    PRIMARY KEY (commit_id, path),
    FOREIGN KEY (commit_id) REFERENCES commits(id) ON DELETE CASCADE
);
```

#### `pull_requests`

Stores PR metadata.

```sql
CREATE TABLE IF NOT EXISTS pull_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    title TEXT,
    body TEXT,
    state TEXT,                    -- open, closed, merged
    author_login TEXT,
    base_branch TEXT,
    head_branch TEXT,
    created_at TEXT,
    updated_at TEXT,
    merged_at TEXT,
    closed_at TEXT,
    additions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    changed_files INTEGER DEFAULT 0,
    commits_count INTEGER DEFAULT 0,
    github_created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(repository_id, number),
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
);
```

#### `pr_commits`

Links PRs to their commits.

```sql
CREATE TABLE IF NOT EXISTS pr_commits (
    pr_id INTEGER NOT NULL,
    commit_id INTEGER NOT NULL,
    PRIMARY KEY (pr_id, commit_id),
    FOREIGN KEY (pr_id) REFERENCES pull_requests(id) ON DELETE CASCADE,
    FOREIGN KEY (commit_id) REFERENCES commits(id) ON DELETE CASCADE
);
```

#### `chat_activity_links`

Cross-reference table linking chats to GitHub activity.

```sql
CREATE TABLE IF NOT EXISTS chat_activity_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    activity_type TEXT NOT NULL,   -- 'commit' or 'pr'
    activity_id INTEGER NOT NULL,  -- commit.id or pull_requests.id
    link_type TEXT NOT NULL,       -- how the link was established
    confidence REAL DEFAULT 1.0,   -- 0.0-1.0 confidence score
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chat_id, activity_type, activity_id),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
```

**Link Types:**
- `workspace_temporal` - Same workspace, activity within time window of chat
- `file_overlap` - Shared files between chat_files and commit_files
- `branch_match` - PR branch name mentioned or matches chat context
- `content_match` - Terms in commit/PR message match chat content
- `manual` - User-assigned link

### Domain Models

```python
@dataclass
class Repository:
    id: Optional[int] = None
    workspace_id: Optional[int] = None
    owner: str = ""
    name: str = ""
    full_name: str = ""
    default_branch: str = "main"
    remote_url: str = ""
    local_path: str = ""
    last_synced_at: Optional[datetime] = None

@dataclass
class Commit:
    id: Optional[int] = None
    repository_id: int = 0
    sha: str = ""
    message: str = ""
    author_name: str = ""
    author_email: str = ""
    author_login: str = ""
    authored_at: Optional[datetime] = None
    committed_at: Optional[datetime] = None
    branch: Optional[str] = None
    additions: int = 0
    deletions: int = 0
    files_changed: int = 0
    files: List[str] = None  # populated from commit_files

@dataclass
class PullRequest:
    id: Optional[int] = None
    repository_id: int = 0
    number: int = 0
    title: str = ""
    body: str = ""
    state: str = "open"  # open, closed, merged
    author_login: str = ""
    base_branch: str = ""
    head_branch: str = ""
    created_at: Optional[datetime] = None
    merged_at: Optional[datetime] = None
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0
    commits_count: int = 0
```

## Cross-Referencing Strategy

### 1. Workspace → Repository Mapping

When a workspace is encountered:
1. Check if `resolved_path` points to a git repository
2. Read `.git/config` to extract remote URL
3. Parse remote URL to get `owner/name`
4. Create/update `repositories` entry linked to workspace

```python
def discover_repository(workspace_path: str) -> Optional[Repository]:
    git_config = Path(workspace_path) / ".git" / "config"
    if not git_config.exists():
        return None
    
    # Parse remote URL from config
    remote_url = parse_git_remote(git_config)
    owner, name = parse_github_url(remote_url)
    
    return Repository(owner=owner, name=name, remote_url=remote_url)
```

### 2. Temporal Correlation

Link chats to activity that occurred around the same time:

```python
def find_temporal_links(chat_id: int, window_hours: int = 24) -> List[ActivityLink]:
    """
    Find commits/PRs within ±window_hours of chat activity.
    
    Uses chat.created_at to chat.last_updated_at as the active period.
    """
    # Get chat time range
    chat = db.get_chat(chat_id)
    start = chat.created_at - timedelta(hours=window_hours)
    end = (chat.last_updated_at or chat.created_at) + timedelta(hours=window_hours)
    
    # Find commits in same workspace repo within window
    commits = db.find_commits_in_range(
        workspace_id=chat.workspace_id,
        start_time=start,
        end_time=end
    )
    
    # Find PRs similarly
    prs = db.find_prs_in_range(...)
    
    return links
```

### 3. File-Based Linking

Link based on shared files between chat and commits:

```python
def find_file_links(chat_id: int) -> List[ActivityLink]:
    """
    Find commits that modified files mentioned in the chat.
    """
    chat_files = db.get_chat_files(chat_id)
    
    # Normalize paths (strip workspace prefix)
    normalized_paths = [normalize_path(f) for f in chat_files]
    
    # Find commits with overlapping files
    commits = db.find_commits_by_files(
        workspace_id=chat.workspace_id,
        file_paths=normalized_paths
    )
    
    # Calculate confidence based on overlap percentage
    for commit in commits:
        commit_files = set(commit.files)
        overlap = len(set(normalized_paths) & commit_files)
        confidence = overlap / max(len(chat_files), 1)
        ...
```

### 4. Content Matching (Optional)

Search for related terms between chat content and commit messages:

```python
def find_content_links(chat_id: int) -> List[ActivityLink]:
    """
    Find commits/PRs with related content using FTS.
    
    This is lower confidence but can catch conceptual relationships.
    """
    # Extract key terms from chat
    chat = db.get_chat(chat_id)
    key_terms = extract_key_terms(chat.messages)
    
    # Search commit messages
    matching_commits = db.search_commits(key_terms)
    
    # Search PR titles/bodies
    matching_prs = db.search_prs(key_terms)
```

## GitHub Reader Service

Uses `gh` CLI (already authenticated) for data fetching:

```python
class GitHubReader:
    """Reads GitHub activity using gh CLI."""
    
    def get_commits(self, repo: str, since: datetime, until: datetime, 
                   branch: str = None) -> List[Dict]:
        """
        Fetch commits from repository.
        
        Uses: gh api repos/{owner}/{repo}/commits
        """
        cmd = [
            "gh", "api",
            f"repos/{repo}/commits",
            "--paginate",
            "-q", ".[] | {sha, message: .commit.message, ...}"
        ]
        ...
    
    def get_pull_requests(self, repo: str, state: str = "all") -> List[Dict]:
        """
        Fetch PRs from repository.
        
        Uses: gh pr list --repo {repo} --json ...
        """
        cmd = [
            "gh", "pr", "list",
            "--repo", repo,
            "--state", state,
            "--json", "number,title,body,state,author,..."
        ]
        ...
    
    def get_pr_commits(self, repo: str, pr_number: int) -> List[str]:
        """Get commit SHAs for a PR."""
        ...
```

## CLI Commands

```bash
# Discover and link repositories to workspaces
python -m src github discover

# Ingest commits from all linked repositories
python -m src github ingest --commits
python -m src github ingest --commits --since 2024-01-01

# Ingest PRs from all linked repositories  
python -m src github ingest --prs
python -m src github ingest --prs --state merged

# Ingest everything
python -m src github ingest --all

# Run cross-referencing to link chats to activity
python -m src github link
python -m src github link --chat-id 123  # specific chat

# View activity for a chat
python -m src github show --chat-id 123

# Search activity
python -m src github search "fix bug"
```

## Web UI Extensions

Add GitHub activity panel to chat detail view:

- **Related Commits**: Commits linked to this chat
- **Related PRs**: PRs linked to this chat  
- **Timeline**: Interleaved view of chat messages and GitHub activity

## Implementation Order

1. **Phase 1: Schema & Models**
   - Add tables to `db.py`
   - Create domain models in `models.py`
   
2. **Phase 2: Repository Discovery**
   - Implement workspace → repo mapping
   - Add `GitHubReader` with `gh` CLI integration
   
3. **Phase 3: Activity Ingestion**
   - Implement commit fetching and storage
   - Implement PR fetching and storage
   
4. **Phase 4: Cross-Referencing**
   - Implement temporal linking
   - Implement file-based linking
   - Add link table population
   
5. **Phase 5: CLI & UI**
   - Add CLI commands
   - Extend web UI with activity panels

## Queries

### Find related activity for a chat

```sql
SELECT 
    cal.activity_type,
    cal.link_type,
    cal.confidence,
    CASE 
        WHEN cal.activity_type = 'commit' THEN c.message
        WHEN cal.activity_type = 'pr' THEN p.title
    END as title,
    CASE
        WHEN cal.activity_type = 'commit' THEN c.authored_at
        WHEN cal.activity_type = 'pr' THEN p.created_at
    END as activity_time
FROM chat_activity_links cal
LEFT JOIN commits c ON cal.activity_type = 'commit' AND cal.activity_id = c.id
LEFT JOIN pull_requests p ON cal.activity_type = 'pr' AND cal.activity_id = p.id
WHERE cal.chat_id = ?
ORDER BY activity_time DESC;
```

### Find chats related to a commit

```sql
SELECT c.*, cal.link_type, cal.confidence
FROM chats c
JOIN chat_activity_links cal ON c.id = cal.chat_id
WHERE cal.activity_type = 'commit' AND cal.activity_id = ?
ORDER BY cal.confidence DESC;
```

### Timeline view (chats + activity interleaved)

```sql
SELECT 
    'chat' as type,
    c.id,
    c.title,
    c.created_at as timestamp,
    w.resolved_path as context
FROM chats c
LEFT JOIN workspaces w ON c.workspace_id = w.id
WHERE c.workspace_id = ?

UNION ALL

SELECT
    'commit' as type,
    cm.id,
    cm.message as title,
    cm.authored_at as timestamp,
    r.full_name as context
FROM commits cm
JOIN repositories r ON cm.repository_id = r.id
WHERE r.workspace_id = ?

ORDER BY timestamp DESC;
```
