## Cursor Chats App DB Schema (`chats.db`)

This document describes the **local aggregation database** schema created/managed by `ChatDatabase` in `src/core/db.py`.

This is **not** Cursor's own `state.vscdb` schema. It's the schema for the consolidated archive DB that this repo writes to (default path is OS-dependent via `get_default_db_path()`).

### Tables

#### `workspaces`

```sql
CREATE TABLE IF NOT EXISTS workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_hash TEXT UNIQUE NOT NULL,
    folder_uri TEXT,
    resolved_path TEXT,
    first_seen_at TEXT,
    last_seen_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

#### `chats`

```sql
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cursor_composer_id TEXT UNIQUE NOT NULL,
    workspace_id INTEGER,
    title TEXT,
    mode TEXT,
    created_at TEXT,
    last_updated_at TEXT,
    source TEXT DEFAULT 'cursor',
    messages_count INTEGER DEFAULT 0,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
```

#### `messages`

```sql
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    text TEXT,
    rich_text TEXT,
    created_at TEXT,
    cursor_bubble_id TEXT,
    raw_json TEXT,
    message_type TEXT DEFAULT 'response',
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
```

#### `chat_files`

```sql
CREATE TABLE IF NOT EXISTS chat_files (
    chat_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    PRIMARY KEY (chat_id, path),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
```

#### `tags`

```sql
CREATE TABLE IF NOT EXISTS tags (
    chat_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (chat_id, tag),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
```

### Full Text Search (FTS5)

#### `message_fts`

This is an FTS5 virtual table indexing message text for search. It uses `messages` as its content table.

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
    chat_id,
    text,
    rich_text,
    content='messages',
    content_rowid='id'
);
```

### Triggers (FTS synchronization)

#### Insert trigger

```sql
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO message_fts(chat_id, text, rich_text, rowid)
    VALUES (new.chat_id, new.text, new.rich_text, new.id);
END;
```

#### Delete trigger

```sql
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO message_fts(message_fts, rowid, chat_id, text, rich_text)
    VALUES('delete', old.id, old.chat_id, old.text, old.rich_text);
END;
```

#### Update trigger

```sql
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO message_fts(message_fts, rowid, chat_id, text, rich_text)
    VALUES('delete', old.id, old.chat_id, old.text, old.rich_text);
    INSERT INTO message_fts(chat_id, text, rich_text, rowid)
    VALUES (new.chat_id, new.text, new.rich_text, new.id);
END;
```

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_chats_composer_id ON chats(cursor_composer_id);
CREATE INDEX IF NOT EXISTS idx_chats_workspace ON chats(workspace_id);
CREATE INDEX IF NOT EXISTS idx_chats_created ON chats(created_at);

CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

CREATE INDEX IF NOT EXISTS idx_workspaces_hash ON workspaces(workspace_hash);
```

### Migrations (auto-applied at runtime)

`ChatDatabase._ensure_schema()` performs lightweight migrations using `PRAGMA table_info(...)` checks:

```sql
-- chats.messages_count
ALTER TABLE chats ADD COLUMN messages_count INTEGER DEFAULT 0;

-- messages.message_type
ALTER TABLE messages ADD COLUMN message_type TEXT DEFAULT 'response';
```

### Notes

- **Timestamps** are stored as TEXT (ISO strings) as written by the application layer.
- `message_type` values are written from the application's `MessageType` enum (currently: `response`, `tool_call`, `thinking`, `empty`).
- `messages_count` is denormalized for list/filter performance; it's set during upsert to `len(chat.messages)` at ingest time.

---

## GitHub Activity Tables

These tables store GitHub commits, PRs, and cross-references to chats.

### `repositories`

Maps workspaces to GitHub repositories.

```sql
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER,
    owner TEXT NOT NULL,
    name TEXT NOT NULL,
    full_name TEXT NOT NULL,
    default_branch TEXT DEFAULT 'main',
    remote_url TEXT,
    local_path TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_synced_at TEXT,
    UNIQUE(owner, name),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
```

### `commits`

Stores commit metadata from GitHub.

```sql
CREATE TABLE IF NOT EXISTS commits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL,
    sha TEXT NOT NULL,
    short_sha TEXT NOT NULL,
    message TEXT,
    author_name TEXT,
    author_email TEXT,
    author_login TEXT,
    authored_at TEXT NOT NULL,
    committed_at TEXT,
    branch TEXT,
    additions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    files_changed INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(repository_id, sha),
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
);
```

### `commit_files`

Files changed in each commit (for cross-referencing with `chat_files`).

```sql
CREATE TABLE IF NOT EXISTS commit_files (
    commit_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    status TEXT,
    additions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    PRIMARY KEY (commit_id, path),
    FOREIGN KEY (commit_id) REFERENCES commits(id) ON DELETE CASCADE
);
```

### `pull_requests`

Stores PR metadata.

```sql
CREATE TABLE IF NOT EXISTS pull_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    title TEXT,
    body TEXT,
    state TEXT DEFAULT 'open',
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

### `pr_commits`

Links PRs to their commits (many-to-many).

```sql
CREATE TABLE IF NOT EXISTS pr_commits (
    pr_id INTEGER NOT NULL,
    commit_id INTEGER NOT NULL,
    PRIMARY KEY (pr_id, commit_id),
    FOREIGN KEY (pr_id) REFERENCES pull_requests(id) ON DELETE CASCADE,
    FOREIGN KEY (commit_id) REFERENCES commits(id) ON DELETE CASCADE
);
```

### `chat_activity_links`

Cross-reference table linking chats to GitHub activity.

```sql
CREATE TABLE IF NOT EXISTS chat_activity_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    activity_type TEXT NOT NULL,    -- 'commit' or 'pr'
    activity_id INTEGER NOT NULL,   -- commits.id or pull_requests.id
    link_type TEXT NOT NULL,        -- how the link was established
    confidence REAL DEFAULT 1.0,    -- 0.0-1.0 confidence score
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chat_id, activity_type, activity_id),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
```

**Link Types:**
- `workspace_temporal` - Same workspace, activity within time window of chat
- `file_overlap` - Shared files between `chat_files` and `commit_files`
- `branch_match` - PR branch name mentioned in chat context
- `content_match` - Terms in commit/PR message match chat content
- `manual` - User-assigned link

### GitHub Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_repos_workspace ON repositories(workspace_id);
CREATE INDEX IF NOT EXISTS idx_repos_full_name ON repositories(full_name);
CREATE INDEX IF NOT EXISTS idx_commits_repo ON commits(repository_id);
CREATE INDEX IF NOT EXISTS idx_commits_sha ON commits(sha);
CREATE INDEX IF NOT EXISTS idx_commits_authored ON commits(authored_at);
CREATE INDEX IF NOT EXISTS idx_commit_files_commit ON commit_files(commit_id);
CREATE INDEX IF NOT EXISTS idx_commit_files_path ON commit_files(path);
CREATE INDEX IF NOT EXISTS idx_prs_repo ON pull_requests(repository_id);
CREATE INDEX IF NOT EXISTS idx_prs_number ON pull_requests(number);
CREATE INDEX IF NOT EXISTS idx_prs_created ON pull_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_prs_state ON pull_requests(state);
CREATE INDEX IF NOT EXISTS idx_activity_links_chat ON chat_activity_links(chat_id);
CREATE INDEX IF NOT EXISTS idx_activity_links_activity ON chat_activity_links(activity_type, activity_id);
```
