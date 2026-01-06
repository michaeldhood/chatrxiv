# How to Rename This Repository

This guide documents the complete process for renaming this project. Last performed: January 2025 (cursor_chats → chatrxiv).

---

## Overview

Renaming this project touches **6 areas**:

1. Package configuration (Python identity)
2. Runtime paths and environment variables
3. UI text and branding
4. Documentation
5. Git and GitHub
6. Database migration

---

## 1. Package Configuration

Update Python package identity.

### Files to Update

| File | What to Change |
|------|----------------|
| `setup.py` | `name`, `url`, `entry_points` console script name |
| `src/__init__.py` | Module docstring |
| `src/core/__init__.py` | Module docstring |
| `src/cli/__init__.py` | CLI help text (line ~25) |
| `src/ui/web/__init__.py` | Module docstring |
| `tests/__init__.py` | Module docstring |

### Example Changes in `setup.py`

```python
# Before
name="old_name",
url="https://github.com/username/old_name",
entry_points={
    "console_scripts": [
        "old-name=src.cli:main",
    ],
},

# After
name="new_name",
url="https://github.com/username/new_name",
entry_points={
    "console_scripts": [
        "new-name=src.cli:main",
    ],
},
```

---

## 2. Runtime Paths and Environment Variables

### Environment Variable

The database path can be overridden via environment variable. Update the variable name in:

| File | Line | Change |
|------|------|--------|
| `src/cli/commands/web.py` | ~36 | `OLD_NAME_DB_PATH` → `NEW_NAME_DB_PATH` |
| `src/ui/web/app.py` | ~45 | `OLD_NAME_DB_PATH` → `NEW_NAME_DB_PATH` |
| `QUICKSTART.md` | ~76 | Environment variable reference |

### Database Folder Paths

Update the application data directory name in `src/core/config.py`:

```python
def get_default_db_path() -> Path:
    system = platform.system()
    home = Path.home()
    
    if system == 'Darwin':  # macOS
        base_dir = home / "Library" / "Application Support" / "NEW_NAME"
    elif system == 'Windows':
        base_dir = home / "AppData" / "Roaming" / "NEW_NAME"
    elif system == 'Linux':
        base_dir = home / ".local" / "share" / "NEW_NAME"
    else:
        base_dir = home / ".NEW_NAME"
    
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "chats.db"
```

---

## 3. UI Text and Branding

### HTML Templates

Update branding in all templates:

| File | What to Change |
|------|----------------|
| `src/ui/web/templates/base.html` | `<title>` tag, `<h1>` header |
| `src/ui/web/templates/index.html` | Any title references |
| `src/ui/web/templates/database.html` | Any title references |
| `src/ui/web/templates/chat_detail.html` | Any title references |
| `src/ui/web/templates/search.html` | Any title references |

### Quick Check

```bash
grep -r "OLD_NAME" src/ui/web/templates/
```

---

## 4. Documentation

### Primary Docs

| File | What to Change |
|------|----------------|
| `README.md` | Title, project description |
| `CLAUDE.md` | Project overview section |
| `QUICKSTART.md` | Database paths, env var references |

### Reference Docs

| File | What to Change |
|------|----------------|
| `docs/PRD.md` | Project name references |
| `docs/plan.md` | Project name references |
| `docs/claude/setup.md` | Database path examples |
| `docs/schema/aggregated-database.md` | Title |

### Quick Check

```bash
grep -ri "old_name\|old-name" docs/ README.md QUICKSTART.md CLAUDE.md
```

---

## 5. Git and GitHub

### Step 1: Rename GitHub Repository

1. Go to `https://github.com/USERNAME/OLD_NAME/settings`
2. Under "Repository name", change to `NEW_NAME`
3. Click "Rename"

GitHub automatically sets up redirects from the old URL.

### Step 2: Update Local Git Remote

```bash
git remote set-url origin https://github.com/USERNAME/NEW_NAME.git
```

### Step 3: Rename Local Directory

```bash
cd /path/to/parent/directory
mv old_name new_name
cd new_name
```

### Verify

```bash
git remote -v
# Should show: origin https://github.com/USERNAME/NEW_NAME.git
```

---

## 6. Database Migration

**Critical**: The database must be moved to the new application data directory.

### Locate Old Database

| OS | Path |
|----|------|
| macOS | `~/Library/Application Support/OLD_NAME/chats.db` |
| Linux | `~/.local/share/OLD_NAME/chats.db` |
| Windows | `%APPDATA%/OLD_NAME/chats.db` |

### Move Database Files

SQLite WAL mode uses three files - **move all of them**:

| File | Purpose |
|------|---------|
| `chats.db` | Main database |
| `chats.db-wal` | Write-ahead log (uncommitted transactions) |
| `chats.db-shm` | Shared memory index |

```bash
# macOS example
mkdir -p ~/Library/Application\ Support/NEW_NAME

mv ~/Library/Application\ Support/OLD_NAME/chats.db \
   ~/Library/Application\ Support/NEW_NAME/chats.db

mv ~/Library/Application\ Support/OLD_NAME/chats.db-shm \
   ~/Library/Application\ Support/NEW_NAME/chats.db-shm

mv ~/Library/Application\ Support/OLD_NAME/chats.db-wal \
   ~/Library/Application\ Support/NEW_NAME/chats.db-wal
```

### Verify Database Works

```bash
python -m src search "test" --limit 3
```

### Alternative: Use Environment Variable

Instead of moving the database, existing users can set the env var to point to the old location:

```bash
export NEW_NAME_DB_PATH=~/Library/Application\ Support/OLD_NAME/chats.db
```

---

## Complete Checklist

```
[ ] 1. Package Configuration
    [ ] setup.py - name, url, entry_points
    [ ] src/__init__.py - docstring
    [ ] src/core/__init__.py - docstring
    [ ] src/cli/__init__.py - CLI help text
    [ ] src/ui/web/__init__.py - docstring
    [ ] tests/__init__.py - docstring

[ ] 2. Runtime Paths
    [ ] src/core/config.py - database paths (4 OS variants)
    [ ] src/cli/commands/web.py - env var name
    [ ] src/ui/web/app.py - env var name

[ ] 3. UI Text
    [ ] src/ui/web/templates/base.html - title, header
    [ ] Other templates as needed

[ ] 4. Documentation
    [ ] README.md
    [ ] CLAUDE.md
    [ ] QUICKSTART.md
    [ ] docs/PRD.md
    [ ] docs/plan.md
    [ ] docs/claude/setup.md
    [ ] docs/schema/aggregated-database.md

[ ] 5. Git/GitHub
    [ ] Rename repo on GitHub
    [ ] Update local remote URL
    [ ] Rename local directory

[ ] 6. Database
    [ ] Move chats.db
    [ ] Move chats.db-shm
    [ ] Move chats.db-wal
    [ ] Verify with search command
```

---

## Grep Commands for Verification

After making changes, verify no old references remain:

```bash
# Check source code (excluding _parallel/ project management files)
grep -ri "old_name" src/ tests/ --include="*.py" --include="*.html"

# Check docs
grep -ri "old_name\|old-name" docs/ README.md QUICKSTART.md CLAUDE.md

# Check config files
grep -ri "old_name" setup.py requirements.txt
```

---

## Migration Notes for Users

If you distribute this tool, document migration for existing users:

1. **Option A**: Move database to new location (see Section 6)
2. **Option B**: Set environment variable pointing to old location

```bash
# Option B example
export NEW_NAME_DB_PATH=~/.old_name/chats.db
```

---

## History

| Date | From | To |
|------|------|----|
| Jan 2025 | cursor_chats | chatrxiv |
