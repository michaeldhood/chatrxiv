# Test Coverage Analysis Report

**Date:** 2025-12-24
**Overall Coverage:** 29% (3850 total statements, 2747 missing)
**Tests Passing:** 48/48 ✓

## Executive Summary

The codebase has **significant testing gaps**, particularly in user-facing components (CLI, Web UI) and critical infrastructure (file watching, export functionality). While core business logic (database, tagging, journal generation) has good coverage (66-94%), most integration points and command-line interfaces are completely untested (0%).

---

## Coverage by Module

### ✅ Well-Tested (>60% Coverage)

| Module | Coverage | Status |
|--------|----------|--------|
| `src/core/models.py` | 94% | Excellent - Domain models well tested |
| `src/tagger.py` | 92% | Excellent - Tag management logic covered |
| `src/journal.py` | 87% | Good - Journal generation tested |
| `src/core/tag_registry.py` | 84% | Good - Registry patterns tested |
| `src/core/db.py` | 66% | Adequate - Core DB operations tested |
| `src/services/search.py` | 65% | Adequate - Search functionality covered |
| `src/readers/workspace_reader.py` | 63% | Adequate - Basic reading tested |

### ⚠️ Partially Tested (20-60% Coverage)

| Module | Coverage | Missing Coverage |
|--------|----------|-----------------|
| `src/core/config.py` | 50% | Platform-specific path resolution untested |
| `src/parser.py` | 43% | CSV/Markdown conversion untested |
| `src/readers/global_reader.py` | 33% | Batch operations, error handling untested |
| `src/services/aggregator.py` | 30% | Chat linking, bubble classification untested |
| `src/extractor.py` | 28% | Cross-platform extraction, WSL support untested |

### ❌ Critically Untested (<20% Coverage)

| Module | Coverage | Impact |
|--------|----------|--------|
| **All CLI Commands** | 0% | **Critical** - User-facing entry points |
| `src/cli/__init__.py` | 0% | High - CLI infrastructure |
| `src/cli/commands/*` | 0% | High - All command implementations |
| `src/ui/web/app.py` | 0% | **Critical** - Entire web UI |
| `src/services/watcher.py` | 0% | High - File watching for incremental updates |
| `src/viewer.py` | 17% | Medium - File browsing functionality |
| `src/services/exporter.py` | 20% | Medium - Export to CSV/Markdown |
| `src/readers/claude_reader.py` | 20% | Medium - Claude.ai integration |
| `src/services/legacy_importer.py` | 14% | Medium - Migration from old format |

---

## Priority Recommendations

### 🔴 Priority 1: Critical User-Facing Functionality

#### 1.1 CLI Command Tests (0% → 70% target)
**Why:** The entire CLI is the primary user interface but has zero test coverage.

**What to test:**
```python
# tests/test_cli_commands.py

def test_ingest_command_basic():
    """Test basic ingest command execution."""
    # Test: cursor-chats ingest --source cursor

def test_ingest_incremental_mode():
    """Test incremental ingestion flag."""
    # Test: cursor-chats ingest --incremental

def test_search_command():
    """Test search command with various queries."""
    # Test: cursor-chats search "Python"

def test_tag_add_remove():
    """Test tag management commands."""
    # Test: cursor-chats tag add <chat-id> tech/python

def test_export_command():
    """Test export to various formats."""
    # Test: cursor-chats export --format markdown

def test_watch_command_lifecycle():
    """Test watch command start/stop."""
    # Test: cursor-chats watch --interval 60
```

**Files to create:**
- `tests/test_cli_commands.py` - Test Click command execution
- `tests/test_cli_integration.py` - End-to-end CLI workflows

**Missing coverage in:**
- `src/cli/commands/database.py:7-199` - All ingest, search, import commands
- `src/cli/commands/extract.py:7-129` - Extraction commands
- `src/cli/commands/tag.py:7-224` - Tag management
- `src/cli/commands/watch.py:6-238` - File watching commands
- `src/cli/commands/web.py:6-61` - Web UI launcher

#### 1.2 Web UI Tests (0% → 60% target)
**Why:** The web interface has zero coverage, risking broken functionality in production.

**What to test:**
```python
# tests/test_web_ui.py

def test_index_page_loads():
    """Test home page renders with chat list."""

def test_search_functionality():
    """Test search returns correct results."""

def test_chat_detail_page():
    """Test individual chat view."""

def test_pagination():
    """Test pagination parameters work."""

def test_tag_filtering():
    """Test filtering by tags."""

def test_sse_stream_connection():
    """Test SSE real-time updates."""
```

**Files to create:**
- `tests/test_web_ui.py` - Flask route tests
- `tests/fixtures/web_fixtures.py` - Test database setup

**Missing coverage in:**
- `src/ui/web/app.py:4-264` - All routes, SSE streaming, templates

---

### 🟡 Priority 2: Core Integration Points

#### 2.1 Chat Aggregator Tests (30% → 75% target)
**Why:** Aggregator orchestrates data extraction and linking, currently only 30% tested.

**What to test:**
```python
# tests/test_aggregator_integration.py

def test_workspace_to_composer_linking():
    """Test linking workspace metadata to composer conversations."""
    # Current gap: lines 154-213, 264-370

def test_bubble_classification():
    """Test message type classification (user/assistant/system)."""
    # Current gap: lines 394-447

def test_conversation_header_resolution():
    """Test resolving full conversations from headers."""
    # Current gap: lines 72-96

def test_incremental_sync():
    """Test incremental updates don't duplicate data."""
    # Current gap: lines 610-625

def test_error_handling_malformed_data():
    """Test graceful handling of corrupted Cursor DB data."""
    # Current gap: lines 732-755
```

**Missing coverage in:**
- `src/services/aggregator.py:72-96, 154-213, 264-370` - Linking logic
- `src/services/aggregator.py:394-447, 610-625` - Message processing
- `src/services/aggregator.py:732-755, 834-940` - Error handling

#### 2.2 File Watcher Tests (0% → 60% target)
**Why:** Automatic ingestion is a key feature but completely untested.

**What to test:**
```python
# tests/test_watcher.py

def test_watcher_detects_db_changes():
    """Test file modification triggers ingestion."""

def test_watcher_debouncing():
    """Test debounce prevents rapid re-ingestion."""

def test_watcher_filters_relevant_files():
    """Test only state.vscdb files trigger ingestion."""

def test_watcher_fallback_polling():
    """Test polling mode when watchdog unavailable."""

def test_watcher_graceful_shutdown():
    """Test clean shutdown of watcher threads."""
```

**Files to create:**
- `tests/test_watcher.py` - File system event tests

**Missing coverage in:**
- `src/services/watcher.py:7-320` - Entire watcher service

#### 2.3 Export Functionality (20% → 70% target)
**Why:** Export is a primary use case but barely tested.

**What to test:**
```python
# tests/test_exporter.py

def test_export_to_csv():
    """Test CSV export with proper formatting."""
    # Current gap: lines 46-84

def test_export_to_markdown():
    """Test Markdown export with code blocks."""
    # Current gap: lines 100-113

def test_export_to_json():
    """Test JSON export preserves structure."""

def test_export_with_tags():
    """Test tags included in exported data."""

def test_export_filtered_chats():
    """Test exporting subset of chats."""
```

**Missing coverage in:**
- `src/services/exporter.py:46-84, 100-113` - Export format logic

---

### 🟢 Priority 3: Edge Cases and Platform Support

#### 3.1 Cross-Platform Extractor Tests (28% → 80% target)
**Why:** Advertised as cross-platform but platform-specific code untested.

**What to test:**
```python
# tests/test_extractor_platforms.py

@pytest.mark.skipif(sys.platform != 'win32', reason='Windows-specific')
def test_windows_path_resolution():
    """Test Windows AppData path resolution."""
    # Current gap: lines 33-53

@pytest.mark.skipif(sys.platform != 'linux', reason='Linux-specific')
def test_wsl_path_conversion():
    """Test WSL path conversion from Windows to Linux."""
    # Current gap: lines 74-80

@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS-specific')
def test_macos_path_resolution():
    """Test macOS Library path resolution."""
    # Current gap: lines 95-123

def test_finds_multiple_workspaces():
    """Test detection of multiple workspace databases."""
    # Current gap: lines 137-161
```

**Missing coverage in:**
- `src/extractor.py:33-53, 74-80, 95-123` - Platform-specific paths
- `src/extractor.py:137-161` - Workspace discovery

#### 3.2 Parser Format Conversion (43% → 75% target)
**Why:** Format conversion is core functionality, only JSON tested.

**What to test:**
```python
# tests/test_parser_formats.py

def test_convert_to_csv_with_code_blocks():
    """Test CSV conversion escapes code properly."""
    # Current gap: lines 76-92

def test_convert_to_markdown_formatting():
    """Test Markdown preserves chat structure."""
    # Current gap: lines 108-133

def test_handle_malformed_json():
    """Test graceful handling of invalid JSON."""
    # Current gap: lines 148-169

def test_preserve_unicode_in_conversion():
    """Test Unicode characters preserved across formats."""
```

**Missing coverage in:**
- `src/parser.py:76-92, 108-133, 148-169` - Format conversion functions

#### 3.3 Claude.ai Reader Tests (20% → 70% target)
**Why:** Integration with Claude.ai chat history is unique feature.

**What to test:**
```python
# tests/test_claude_reader.py

def test_read_claude_api_credentials():
    """Test DLT secrets integration."""
    # Current gap: lines 45-71

def test_fetch_claude_conversations():
    """Test API conversation fetching."""
    # Current gap: lines 80-90, 118-146

def test_handle_api_rate_limits():
    """Test rate limit handling."""

def test_pagination_of_conversations():
    """Test fetching paginated results."""
```

**Missing coverage in:**
- `src/readers/claude_reader.py:45-71, 80-90, 118-146` - API integration

---

## Test Infrastructure Improvements

### Add Test Utilities

```python
# tests/conftest.py - Add shared fixtures

@pytest.fixture
def sample_cursor_db():
    """Create sample Cursor database with test data."""

@pytest.fixture
def sample_chats():
    """Generate sample chat data for testing."""

@pytest.fixture
def temp_workspace():
    """Create temporary workspace structure."""

@pytest.fixture
def mock_cursor_paths(monkeypatch):
    """Mock Cursor installation paths."""
```

### Add Integration Test Suite

```python
# tests/integration/test_full_workflow.py

def test_extract_convert_export_workflow():
    """Test complete workflow from extraction to export."""
    # 1. Extract from Cursor DB
    # 2. Ingest to local DB
    # 3. Add tags
    # 4. Export to Markdown
    # 5. Verify output
```

### Add Performance Tests

```python
# tests/performance/test_large_datasets.py

def test_ingest_1000_chats():
    """Test performance with large chat volume."""

def test_search_performance():
    """Test search response time with large DB."""
```

---

## Testing Best Practices

### 1. Use Click's Testing Framework
```python
from click.testing import CliRunner

def test_cli_command():
    runner = CliRunner()
    result = runner.invoke(ingest, ['--source', 'cursor'])
    assert result.exit_code == 0
```

### 2. Mock External Dependencies
```python
@patch('src.readers.claude_reader.dlt')
def test_claude_reader_without_api(mock_dlt):
    """Test Claude reader without hitting API."""
```

### 3. Use Temporary Databases
```python
@pytest.fixture
def isolated_db():
    """Each test gets isolated database."""
    with tempfile.NamedTemporaryFile() as f:
        yield ChatDatabase(f.name)
```

### 4. Test Error Paths
```python
def test_handles_corrupted_database():
    """Test graceful handling of corrupted SQLite file."""

def test_handles_missing_permissions():
    """Test error message when DB not writable."""
```

---

## Metrics to Track

### Coverage Goals (6 months)
- Overall: 29% → **70%**
- CLI: 0% → **70%**
- Web UI: 0% → **60%**
- Core services: 40% → **80%**
- Readers: 40% → **75%**

### Test Count Goals
- Current: 48 tests
- Target: **150+ tests** (3x increase)
  - CLI: +40 tests
  - Integration: +30 tests
  - Edge cases: +32 tests

---

## Quick Wins (Implement First)

1. **CLI smoke tests** (2 hours) - Test each command executes without crashing
2. **Web UI route tests** (3 hours) - Test all routes return 200 OK
3. **Aggregator linking tests** (2 hours) - Test workspace→composer linking
4. **Export format tests** (2 hours) - Test CSV/Markdown generation
5. **Error handling tests** (3 hours) - Test NULL handling, file not found

**Total quick win effort:** ~12 hours for +15% coverage

---

## Files to Create

### New Test Files Needed
1. `tests/test_cli_commands.py` - CLI command execution
2. `tests/test_cli_integration.py` - End-to-end CLI workflows
3. `tests/test_web_ui.py` - Flask routes and templates
4. `tests/test_watcher.py` - File watching functionality
5. `tests/test_exporter.py` - Export format generation
6. `tests/test_extractor_platforms.py` - Cross-platform paths
7. `tests/test_parser_formats.py` - Format conversions
8. `tests/test_claude_reader.py` - Claude.ai integration
9. `tests/test_aggregator_integration.py` - Chat linking
10. `tests/integration/test_full_workflow.py` - E2E workflows

### Test Utilities Needed
1. `tests/conftest.py` - Shared fixtures
2. `tests/fixtures/sample_data.py` - Test data generators
3. `tests/fixtures/mock_cursor_db.py` - Mock Cursor databases
4. `tests/utils/assertions.py` - Custom assertions

---

## Conclusion

The project has **solid unit test coverage for core business logic** (tagging, journaling, database models) but **critical gaps in user-facing components**. The CLI and Web UI—the primary ways users interact with the tool—are completely untested.

**Immediate action items:**
1. Add CLI smoke tests to catch basic breakage
2. Add Web UI route tests for all endpoints
3. Test aggregator linking logic (core functionality)
4. Add integration tests for full workflows
5. Test cross-platform extractor functionality

Implementing the Priority 1 recommendations would increase coverage from **29% to ~55%** and dramatically reduce the risk of shipping broken features to users.
