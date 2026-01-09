# chatrxiv

A collection of tools for extracting, processing, and viewing chat logs from the Cursor AI editor.

## Overview

This project provides utilities to extract chat data from Cursor's SQLite database, convert it to various formats (CSV, JSON, Markdown), and view the contents of chat files. The goal is to make your Cursor chat history more accessible, portable, and analyzable.

## Features

- **Chat Data Extraction**: Extract chat data directly from Cursor's SQLite database
- **Multiple Output Formats**: Convert your chats to CSV, JSON, or Markdown formats
- **Chat Viewer**: Browse and view your chat files with a simple command-line interface
- **Cross-Platform Support**: Works on Windows, macOS, and Linux (including WSL)
- **Smart Tagging System**: Automatically tag chats by programming language, framework, and topic
- **Tag Management**: Add, remove, search, and organize chats with hierarchical tags

## Project Components

- **extractor.py**: Handles the extraction of chat data from Cursor's SQLite database
- **parser.py**: Processes the extracted data and converts it to different formats
- **main.py**: Command-line interface for interacting with the extraction and conversion tools
- **view_chats.py**: A utility script for browsing and viewing chat files

## Usage

Add `--verbose` to any command to see detailed logging output.

### Extracting Chat Data

To extract chat data from your Cursor installation:

```bash
python -m src extract
python -m src extract --verbose  # detailed logging

# Extract to a custom directory
python -m src extract --output-dir ./my_extracts

# Use a custom filename pattern
python -m src extract --filename-pattern "cursor_{workspace}_backup.json"

# Combine options
python -m src extract -o ./backups --filename-pattern "{workspace}_chats.json"
```

This will create JSON files containing your chat data.

### Converting to CSV

To convert an extracted JSON file to CSV format:

```bash
python -m src convert chat_data_[hash].json

# Save to a custom directory
python -m src convert chat_data_[hash].json --output-dir ./csv_exports

# Use a custom output filename
python -m src convert chat_data_[hash].json --output-file my_chats.csv

# Combine options
python -m src convert chat_data_[hash].json -o ./exports --output-file cursor_backup.csv
```

### Converting to Markdown

To convert an extracted JSON file to Markdown format:

```bash
python -m src convert chat_data_[hash].json --format markdown --output-dir markdown_chats
```

### Viewing Chat Files

To browse and view your chat files:

```bash
python -m src view                   # List all chat files
python -m src view chat_filename.md  # View a specific chat file
```

### Managing Tags

The tagging system helps organize and categorize your chat conversations. Tags are stored in the database:

```bash
# Auto-tag all chats in the database
python -m src tag auto-tag-all

# Manually add tags to a chat
python -m src tag add [chat_id] python api testing

# Remove tags from a chat
python -m src tag remove [chat_id] testing

# List all tags with usage counts
python -m src tag list --all

# List tags for a specific chat
python -m src tag list [chat_id]

# Find chats by tag (supports wildcards)
python -m src tag find "tech/python"
python -m src tag find "topic/*"
python -m src tag find "*/api"
```

Tags are hierarchical and normalized (lowercase, spaces become hyphens). The auto-tagger recognizes:
- **Languages**: Python, JavaScript, TypeScript, Java, C++, Rust, Go, Ruby, PHP, Swift
- **Frameworks**: React, Vue, Angular, Django, Flask, Express, Spring, Rails, FastAPI, Next.js
- **Topics**: API/REST, databases, testing, Docker/Kubernetes, Git, CI/CD, security, performance, debugging
- **AI/ML**: Machine learning, LLMs, NLP, computer vision

### Batch Processing

Process multiple files at once with the `--all` flag or use the `batch` command:

```bash
# Convert all JSON files to markdown
python -m src convert --all --format markdown

# Convert all files matching a pattern
python -m src convert --all --pattern "chat_data_2024*.json" --format csv

# Run complete pipeline: extract, convert to markdown, and tag
python -m src batch

# Run specific batch operations
python -m src batch --convert --tag  # Skip extraction (requires database for tagging)
python -m src batch --extract --convert --format csv  # Extract and convert to CSV

# Specify output directory for batch operations
python -m src batch --output-dir ./my_exports
```

### Database Operations

The new CLI uses a local SQLite database for storing and managing chats:

```bash
# Ingest chats from Cursor databases into local DB
python -m src ingest

# Ingest from specific sources
python -m src ingest --source cursor
python -m src ingest --source claude
python -m src ingest --source all

# Incremental ingestion (faster, only new/updated chats)
python -m src ingest --incremental

# Import legacy JSON files to database
python -m src import-legacy chat_data_*.json
python -m src import-legacy . --pattern "chat_data_*.json"

# Search chats in database
python -m src search "python api"

# Export chats from database
python -m src export --format markdown --output-dir exports
python -m src export --chat-id 123  # Export specific chat

# Watch for changes and auto-ingest (daemon mode)
python -m src watch

# Update chat modes without full re-ingest
python -m src update-modes
```

### Web Interface

Start the web UI to browse chats. **One command does everything:**

```bash
python -m src web
```

This single command:
- Serves the web UI at http://localhost:5000
- Watches Cursor's database files for new chats
- Auto-ingests new chats when detected  
- Pushes live updates to the browser via SSE

**Options:**
```bash
# With auto-reload for development
python -m src web --reload

# Disable file watching (just serve existing chats)
python -m src web --no-watch

# Custom host/port
python -m src web --host 0.0.0.0 --port 8080
```

**For Next.js frontend development** (optional, requires Node.js 18+):

```bash
# Install Node.js dependencies (first time only)
cd web && npm install && cd ..

# Run API + Next.js frontend concurrently
npm run dev
# Then open http://localhost:3000 (Next.js hot reload)
```

The web interface includes:
- **Auto-ingest**: New Cursor chats appear automatically (no separate `watch` command needed)
- **Live updates**: SSE pushes changes to your browser in real-time
- **Instant search**: Typeahead search with keyboard navigation (⌘K)
- **Multiple views**: List view and database/spreadsheet view
- **Full-text search**: Search across all chat content with tag and workspace facets
- **Dark theme**: VS Code-inspired dark theme

## File Naming Convention

The exported files follow these naming conventions:
- **JSON extraction**: `chat_data_[workspace_hash].json`
- **Markdown files**: `chat_[workspace_hash]_[id].md`
- **CSV files**: `chat_data_[hash].csv`

## Installation

**Requirements:**
- Python 3.8+
- Node.js 18+ and npm (for web UI)

**Install Python dependencies:**
```bash
pip install -r requirements.txt
```

**Install Node.js dependencies (for web UI):**
```bash
cd web && npm install && cd ..
```

The web UI is optional - CLI commands work without Node.js.

## Development

This project evolved from a simple script to extract Cursor chat logs to a more robust set of tools for working with chat data. Contributions and improvements are welcome!

## Notes

- The extraction process does not modify your original Cursor database
- Cursor stores chat data in SQLite databases which may change format in future versions 
