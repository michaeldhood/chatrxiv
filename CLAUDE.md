# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

chatrxiv is a collection of Python tools for extracting, processing, and viewing chat logs from the Cursor AI editor. The project extracts data from Cursor's SQLite databases and converts it to multiple formats (CSV, JSON, Markdown) for analysis and preservation.

## Development Commands

### Setup
```bash
pip install -r requirements.txt
# or
pip install -e .
```

### Core Operations
```bash
# Extract chat data from Cursor database
python -m src extract
python -m src extract --verbose  # with detailed logging

# Convert JSON to CSV format
python -m src convert chat_data_[hash].json

# Convert to Markdown format
python -m src convert chat_data_[hash].json --format markdown --output-dir markdown_chats

# Browse exported chat files
python -m src view                   # List all chat files
python -m src view chat_filename.md  # View specific file
```

### Testing
```bash
python -m pytest tests/
```

## Architecture

The codebase follows a modular architecture with clear separation of concerns:

- **`src/cli/`** - Click-based command-line interface (modular architecture)
- **`src/__main__.py`** - Entry point for `python -m src` execution
- **`src/extractor.py`** - Cross-platform database extraction from Cursor's SQLite files
- **`src/parser.py`** - Data processing and format conversion (JSON → CSV/Markdown)
- **`src/viewer.py`** - File browser and viewer for exported chat data

## Key Implementation Details

### Database Extraction
- Targets Cursor's `state.vscdb` files in workspace storage directories
- Cross-platform path resolution (Windows/Linux/WSL/macOS supported)
- Extracts chat data from the `ItemTable` where keys contain chat-related patterns
- Uses proper logging with configurable verbosity levels

### Data Processing Pipeline
1. Raw SQLite extraction → JSON format with structured data
2. JSON parsing → pandas DataFrame with proper error handling
3. Export to CSV or structured Markdown with organized file naming
4. Files grouped by workspace hash for organization

### File Naming Convention
- JSON: `chat_data_[workspace_hash].json`
- CSV: `chat_data_[hash].csv`
- Markdown: `chat_[workspace_hash]_[id].md` in specified output directory

### Module Structure
- Package can be run as `python -m src` with subcommands
- Proper logging configuration with --verbose flag support
- Type hints throughout for better code maintainability
- Comprehensive error handling and user feedback

## Cross-Platform Support

The extractor supports all major platforms:
- **Windows**: `%USERPROFILE%\AppData\Roaming\Cursor\User\workspaceStorage`
- **Linux/WSL**: Automatic detection and path conversion
- **macOS**: `~/Library/Application Support/Cursor/User/workspaceStorage`