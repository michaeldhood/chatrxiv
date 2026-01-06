## chatrxiv App DB Schema (`chats.db`)

This document describes the **local aggregation database** schema created/managed by `ChatDatabase` in `src/core/db.py`.

This is **not** Cursor’s own `state.vscdb` schema. It’s the schema for the consolidated archive DB that this repo writes to (default path is OS-dependent via `get_default_db_path()`).

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
- `message_type` values are written from the application’s `MessageType` enum (currently: `response`, `tool_call`, `thinking`, `empty`).
- `messages_count` is denormalized for list/filter performance; it’s set during upsert to `len(chat.messages)` at ingest time.







