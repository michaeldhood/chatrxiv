# Quick Start Guide

## New Architecture

This project now uses a **database-centric architecture** to aggregate all Cursor chats into a single searchable database.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Basic Usage

### 1. Ingest chats from Cursor

Import all chats from your Cursor installation:

```bash
python -m src ingest
```

This will:
- Read all workspace databases (`workspaceStorage/*/state.vscdb`)
- Read the global composer database (`globalStorage/state.vscdb`)
- Link composers to workspaces
- Store everything in a local SQLite database

### 2. Import legacy exports (optional)

If you have old `chat_data_*.json` files from previous extractions:

```bash
python -m src import-legacy .
# Or import a specific file:
python -m src import-legacy chat_data_abc123.json
```

### 3. Search chats

Search all your chats:

```bash
python -m src search "python"
python -m src search "dbt models" --limit 10
```

### 4. Export chats

Export chats to Markdown:

```bash
python -m src export --output-dir exports
# Export a specific chat:
python -m src export --chat-id 123 --output-dir exports
```

### 5. Web UI

Start the web interface:

```bash
# Single command does everything:
python -m src web

# With auto-reload for development:
python -m src web --reload
```

This single command:
- Serves the web UI at http://localhost:5000
- Watches Cursor's database files for new chats
- Auto-ingests new chats when detected
- Pushes live updates to the browser via SSE

**For Next.js frontend development** (optional, requires Node.js):

```bash
# Install Node.js dependencies (first time only)
cd web && npm install && cd ..

# Run API + Next.js frontend concurrently
npm run dev
# Then open http://localhost:3000 (Next.js) instead of :5000
```

The web UI features:
- **Auto-ingest** - New Cursor chats appear automatically
- **Instant search** with ⌘K shortcut
- **Live updates** via Server-Sent Events
- **List and database views** for browsing chats
- **Full-text search** with tag/workspace filters

## Database Location

The database is stored at:
- **macOS**: `~/Library/Application Support/chatrxiv/chats.db`
- **Linux**: `~/.local/share/chatrxiv/chats.db`
- **Windows**: `%APPDATA%/chatrxiv/chats.db`

Override with `--db-path` flag or `CHATRXIV_DB_PATH` environment variable.

## Migration from Old System

The old `extract` and `convert` commands still work for backward compatibility, but the new workflow is:

1. `ingest` - Import from Cursor databases
2. `import-legacy` - Import old JSON exports
3. `search` / `web` - Browse and search
4. `export` - Export to Markdown/JSON

## Next Steps

- Run `python -m src ingest` to populate your database
- Start the web UI with `python -m src web`
- Search your chats with `python -m src search "your query"`

