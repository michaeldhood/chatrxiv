# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

chatrxiv is a multi-source chat aggregation system that extracts, processes, and views chat conversations from Cursor AI, Claude.ai, ChatGPT, and Claude Code. The project uses an ELT (Extract-Load-Transform) architecture with SQLite databases for both raw data preservation and normalized chat storage, plus a Next.js web interface for browsing.

## Development Commands

### Setup
```bash
# Python dependencies
pip install -r requirements.txt

# Install in development mode (optional)
pip install -e .

# Web UI dependencies (optional, requires Node.js 18+)
cd web && npm install && cd ..
```

### Database Operations (Primary Workflow)
```bash
# Ingest from all sources (Cursor, Claude.ai, ChatGPT, Claude Code)
python -m src ingest
python -m src ingest --source cursor      # Single source
python -m src ingest --incremental        # Only new/updated chats

# Search chats in database
python -m src search "python api"

# Export from database
python -m src export --format markdown --output-dir exports
python -m src export --chat-id 123        # Export specific chat

# Import legacy JSON files to database
python -m src import-legacy chat_data_*.json

# Watch for changes and auto-ingest (daemon mode)
python -m src watch

# Update chat modes without full re-ingest
python -m src update-modes
```

### ELT Pipeline (Advanced)
```bash
# Extract raw data to raw.db (preservation layer)
python -m src extract-raw --source cursor

# Transform raw data from raw.db to normalized chats.db
python -m src transform-raw --source cursor

# Combined ELT workflow (extract + transform)
python -m src ingest --source cursor
```

### Legacy Extract/Convert (File-based, deprecated in favor of database workflow)
```bash
# Extract to JSON files
python -m src extract --verbose
python -m src extract --output-dir ./my_extracts --filename-pattern "{workspace}_chats.json"

# Convert JSON to CSV/Markdown
python -m src convert chat_data_[hash].json
python -m src convert chat_data_[hash].json --format markdown --output-dir markdown_chats

# Batch convert all files
python -m src convert --all --format markdown
python -m src batch  # Extract + convert + tag
```

### Tag Management
```bash
# Auto-tag all chats in database
python -m src tag auto-tag-all

# Manually add/remove tags
python -m src tag add [chat_id] python api testing
python -m src tag remove [chat_id] testing

# List and search tags
python -m src tag list --all              # All tags with counts
python -m src tag list [chat_id]          # Tags for specific chat
python -m src tag find "tech/python"      # Find by tag (supports wildcards)
```

### Web Interface
```bash
# Start web server (API + auto-ingest + SSE updates)
python -m src web                         # http://localhost:5000
python -m src web --reload                # With auto-reload for development
python -m src web --no-watch              # Disable file watching

# For Next.js frontend development (optional)
npm run dev                               # Runs API + Next.js concurrently
# Then open http://localhost:3000
```

### Project Management
```bash
# List projects and assign workspaces
python -m src project list
python -m src project create "My Project"
python -m src project assign <workspace_id> <project_id>
```

### Testing
```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_extractor_cursor.py

# Run with verbose output
python -m pytest tests/ -v

# Run tests matching a pattern
python -m pytest tests/ -k "test_cursor"
```

## Architecture

### High-Level Structure

The project uses a **dual-database ELT architecture**:

1. **raw.db**: Archive of raw JSON extracts from all sources (Extract-Load)
2. **chats.db**: Normalized domain models with FTS search (Transform)

This separation enables:
- Raw data preservation for re-transformation
- Independent backup strategies
- Version migration without data loss

### Directory Structure

```
src/
├── cli/                    # Click-based CLI with modular commands
│   ├── commands/          # Command modules (database, extract, tag, web, etc.)
│   ├── orchestrators/     # High-level workflow orchestrators (ingestion, batch)
│   └── context.py         # Shared CLI context and database connections
├── core/                  # Core domain logic
│   ├── models.py          # Pydantic domain models (Chat, Message, Workspace)
│   ├── config.py          # Configuration management
│   ├── source_schemas/    # Source-specific data schemas (cursor, claude, chatgpt)
│   └── db/               # Database layer
│       ├── connection.py  # DatabaseConnection with WAL mode and cleanup
│       ├── schema.py      # SchemaManager (tables, FTS, triggers, migrations)
│       ├── raw_storage.py # RawStorage for raw.db ELT archive
│       ├── repositories/  # Repository pattern (chat, workspace, tag, project)
│       └── search/        # FTS search implementations (instant, filtered, fts)
├── extractors/            # Extract raw data from sources (cursor, claude, chatgpt)
├── transformers/          # Transform raw data to domain models
├── readers/               # Legacy file-based readers (workspace, global, plan)
├── services/              # Business logic layer
│   └── aggregator.py      # ChatAggregator orchestrates extraction + transformation
├── api/                   # FastAPI web server
│   ├── main.py           # FastAPI app with SSE streaming
│   ├── routes/           # API route handlers
│   └── deps.py           # Dependency injection
└── __main__.py           # Entry point for python -m src

web/                       # Next.js 14+ frontend
├── app/                  # App router pages
├── components/           # React components
└── lib/                  # Client utilities

tests/                    # Pytest test suite
```

### Key Architectural Patterns

**Repository Pattern**: Database operations isolated in `src/core/db/repositories/` with base class providing common utilities.

**ELT Pipeline**:
- **Extractors** (`src/extractors/`) → raw data from sources → `raw.db`
- **Transformers** (`src/transformers/`) → raw data → domain models → `chats.db`
- **ChatAggregator** (`src/services/aggregator.py`) orchestrates the full pipeline

**Multi-Source Support**: Each source (Cursor, Claude.ai, ChatGPT, Claude Code) has:
- Schema definition in `src/core/source_schemas/`
- Extractor in `src/extractors/`
- Transformer in `src/transformers/`
- Reader (legacy) in `src/readers/`

**FTS Search**: SQLite FTS5 virtual tables with:
- `message_fts`: Message-level full-text search
- `unified_fts`: Chat-level aggregated search (Obsidian-style)
- Triggers for automatic index updates

**Database Connection Management**:
- WAL mode enabled for concurrent reads
- Automatic cleanup in CLI context callbacks
- Proper transaction handling in repositories

### Data Flow

**Ingestion Flow** (recommended):
```
Source (Cursor/Claude/ChatGPT)
  → Extractor
  → RawStorage (raw.db)
  → Transformer
  → ChatRepository (chats.db)
  → FTS indexes updated via triggers
```

**Legacy Extract Flow** (file-based):
```
Cursor state.vscdb
  → extractor.py
  → JSON files
  → parser.py
  → CSV/Markdown files
```

**Web UI Flow**:
```
Browser
  ← Next.js frontend (http://localhost:3000)
  ← FastAPI API (http://localhost:5000)
  ← ChatRepository
  ← chats.db + FTS search

File watcher (optional)
  → Auto-ingest on Cursor changes
  → SSE stream updates to browser
```

## Key Implementation Details

### Database Schema (chats.db)

**Core Tables**:
- `projects`: Project grouping for workspaces
- `workspaces`: Cursor workspace metadata (hash, folder_uri, project_id)
- `chats`: Conversations (cursor_composer_id, workspace_id, title, mode, source, model, estimated_cost)
- `messages`: Chat messages (chat_id, role, text, rich_text, message_type, raw_json)
- `tags`: Chat tags (chat_id, tag) with hierarchical normalization
- `chat_files`: Relevant files per chat (chat_id, path)
- `plans`: Plan metadata (plan_id, name, file_path)
- `chat_plans`: Chat-plan relationships (chat_id, plan_id, relationship)
- `cursor_activity`: Usage tracking (date, kind, model, tokens, cost)
- `ingestion_state`: Incremental ingestion tracking (source, last_run_at, stats)

**FTS Tables**:
- `message_fts`: Full-text search on messages (chat_id, text, rich_text)
- `unified_fts`: Chat-level search (chat_id, content_type, title, message_text, tags, files)

**Indexes**: Created on frequently queried columns (composer_id, workspace_id, created_at, model, cost, etc.)

### Source-Specific Details

**Cursor**:
- Reads from `state.vscdb` in workspace storage directories
- Extracts from `ItemTable` with chat-related keys
- Links workspace metadata to global composer conversations
- Handles bubble structure (user prompts + AI responses)
- Detects chat modes (agent, normal, chat) from agentic events

**Claude.ai**:
- Reads from exported conversations.json
- Requires session token extraction (see `scripts/get_claude_token.py`)
- Maps chat_messages array to domain models
- Handles thinking blocks as separate message type

**ChatGPT**:
- Reads from exported conversations.json
- Maps mapping dict to messages
- Handles conversation metadata

**Claude Code**:
- Reads from local Claude Code database
- Extracts from conversation tables
- Similar structure to Claude.ai

### Cross-Platform Support

Cursor workspace detection:
- **macOS**: `~/Library/Application Support/Cursor/User/workspaceStorage`
- **Windows**: `%USERPROFILE%\AppData\Roaming\Cursor\User\workspaceStorage`
- **Linux/WSL**: Automatic detection with path conversion

### Web Interface

**Architecture**: Next.js 14+ frontend + FastAPI backend

**Key Features**:
- Instant search with typeahead (⌘K)
- Live updates via Server-Sent Events (SSE)
- Auto-ingest when file watcher detects new chats
- List view and database/spreadsheet view
- Tag and workspace faceted filtering
- Dark theme (VS Code-inspired)

**Development**:
- Backend: `python -m src web --reload` (FastAPI uvicorn)
- Frontend: `cd web && npm run dev` (Next.js hot reload)
- Combined: `npm run dev` (runs both concurrently)

### Tag System

Tags are hierarchical and normalized:
- Lowercase conversion
- Space → hyphen normalization
- Hierarchical structure: `tech/python/api`
- Auto-tagger recognizes languages, frameworks, topics, AI/ML patterns
- Wildcard search support: `tech/*`, `*/api`, `topic/debug*`

## Common Development Tasks

### Adding a New Chat Source

1. Create schema in `src/core/source_schemas/your_source.py`
2. Create extractor in `src/extractors/your_source.py` (implements `extract()` method)
3. Create transformer in `src/transformers/your_source.py` (implements `transform(raw_data)`)
4. Add to `ChatAggregator.VALID_SOURCES` in `src/services/aggregator.py`
5. Register in extractors/transformers dicts in `ChatAggregator._init_extractors()` and `_init_transformers()`
6. Add CLI command handler in `src/cli/commands/database.py`

### Database Migrations

Schema migrations are applied automatically in `SchemaManager.ensure()`:
- Add new column check in `_migrate_[table]_table()` methods
- Use `PRAGMA table_info()` to check existing columns
- Apply `ALTER TABLE ADD COLUMN` for new columns
- Add backfill queries if needed for existing data

### Testing Strategy

Tests are in `tests/` directory:
- `test_extractor_*.py`: Source-specific extraction tests
- `test_transformer_*.py`: Transformation logic tests
- `test_source_schemas.py`: Schema validation tests
- `test_db_*.py`: Database and repository tests
- `test_raw_storage.py`: ELT raw storage tests

Use pytest fixtures for database setup/teardown.

## File Naming Conventions

- **Raw extracts**: Stored in `raw.db` with source and source_id
- **Legacy JSON**: `chat_data_[workspace_hash].json`
- **Legacy CSV**: `chat_data_[hash].csv`
- **Legacy Markdown**: `chat_[workspace_hash]_[id].md`
- **Database**: `chats.db` (normalized) and `raw.db` (raw archive)