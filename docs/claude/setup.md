# API Discovery Process

This document describes the standardized process for discovering and documenting internal web application APIs (like Claude.ai, ChatGPT, etc.) using browser DevTools and HAR file analysis.

## Overview

Instead of manually copy-pasting individual network requests, we use **HAR (HTTP Archive)** files - a standardized format that captures all browser network traffic in a single exportable file.

**Time savings**: ~30 minutes of manual copy-paste → ~2 minutes with HAR export

---

## The Process

### Step 1: Prepare the Browser

1. Open the target web application in Chrome/Firefox/Edge
2. **Log in** with your credentials (API endpoints require authentication)
3. Open DevTools (F12 or Cmd+Option+I)
4. Go to the **Network** tab
5. Ensure "Preserve log" is checked (to keep requests across page navigations)
6. Optional: Clear existing requests for a clean capture

### Step 2: Capture Traffic

Exercise the features you want to document:

| To Document | Actions to Take |
|-------------|-----------------|
| Conversations | Open conversations, send messages, receive responses |
| Settings | Visit settings pages, toggle options |
| File uploads | Upload an image or document |
| Artifacts | Create or view artifacts |
| Projects | Create/switch projects |
| Search | Use search functionality |
| Streaming | Send a message and let it stream back |

**Tip**: Be thorough but focused. Each action generates network requests that will be documented.

### Step 3: Export HAR File

1. Right-click anywhere in the Network tab
2. Select **"Save all as HAR with content"**
3. Save the file (e.g., `claude-2025-12-29.har`)

**Important**: HAR files contain your session cookies and potentially sensitive data. Do not share them publicly.

### Step 4: Run the Parser

```bash
# Basic usage
python scripts/api_discovery/har_parser.py claude.har --output docs/claude/api-reference.md --app-name "Claude.ai"

# With verbose output to see what's being captured
python scripts/api_discovery/har_parser.py claude.har -v --output docs/claude/api-reference.md --app-name "Claude.ai"

# Custom API patterns (if the app doesn't use /api/)
python scripts/api_discovery/har_parser.py openai.har --api-pattern "/backend-api/" --api-pattern "/v1/"
```

### Step 5: Review and Refine

The auto-generated documentation is a starting point. You should:

1. **Add context** - What does each endpoint actually do?
2. **Document parameters** - What are the query params and body fields for?
3. **Add examples** - Realistic request/response examples
4. **Note gotchas** - Rate limits, auth requirements, error responses
5. **Remove noise** - Analytics endpoints you don't care about

---

## Application-Specific Notes

### Claude.ai

**API Patterns**: `/api/`, `a-api.anthropic.com`

**Key Endpoints to Capture**:
- Open any conversation → GET conversation
- Send a message → POST completion (streaming)
- View artifacts → GET artifacts
- Change settings → Various settings endpoints

**Auth**: Session cookies (automatic via browser)

### ChatGPT / OpenAI

**API Patterns**: `/backend-api/`, `chat.openai.com/api/`

**Key Endpoints to Capture**:
- Chat history → conversation list
- Send message → POST conversation
- GPT-4/DALL-E usage → generation endpoints

**Auth**: Session cookies + potentially `__cf_bm` Cloudflare token

### Notion

**API Patterns**: `/api/v3/`, `notion-api.workers.dev`

**Key Endpoints to Capture**:
- Page loads → getPage, loadPageChunk
- Edits → submitTransaction
- Search → search

**Auth**: Session cookies

---

## Extracting Session Cookies for Readers

After discovering APIs via HAR files, you can use the `ClaudeReader` and `ChatGPTReader` classes to programmatically fetch conversations. These readers require session cookies/tokens extracted from your browser.

### For Claude.ai

1. Open **claude.ai** in your browser and ensure you're logged in
2. Open **DevTools** (F12 or Cmd+Option+I)
3. Go to **Application** tab → **Cookies** → `https://claude.ai`
4. Find the cookie named **`sessionKey`**
5. Copy its **Value**
6. Set as environment variable:
   ```bash
   export CLAUDE_SESSION_COOKIE="<paste-value-here>"
   ```
7. Also get your **Organization ID**:
   - Visit `https://claude.ai/settings/account`
   - The URL will contain `?organizationId=YOUR-ORG-ID-HERE`
   - Or check the Network tab when loading that page
   ```bash
   export CLAUDE_ORG_ID="<your-org-id>"
   ```

**Usage:**
```python
from src.readers import ClaudeReader

reader = ClaudeReader()  # Uses env vars automatically
conversations = reader.get_conversation_list()
```

### For ChatGPT

1. Open **chatgpt.com** in your browser and ensure you're logged in
2. Open **DevTools** (F12 or Cmd+Option+I)
3. Go to **Application** tab → **Cookies** → `https://chatgpt.com`
4. Find the cookie named **`__Secure-next-auth.session-token`**
5. Copy its **Value**
6. Set as environment variable:
   ```bash
   export CHATGPT_SESSION_TOKEN="<paste-value-here>"
   ```

**Usage:**
```python
from src.readers import ChatGPTReader

reader = ChatGPTReader()  # Uses env var automatically
conversations = reader.get_conversation_list()
```

### Alternative: dlt Secrets

Instead of environment variables, you can use dlt secrets (`.dlt/secrets.toml`):

```toml
[sources.claude_conversations]
org_id = "your-org-id-here"
session_cookie = "your-session-cookie-here"

[sources.chatgpt_conversations]
session_token = "your-session-token-here"
```

**Security Note:** Session cookies are sensitive - they provide full access to your account. Never commit them to git or share them publicly.

---

## HAR File Structure

Understanding HAR helps with debugging:

```json
{
  "log": {
    "version": "1.2",
    "creator": { "name": "Chrome", "version": "..." },
    "entries": [
      {
        "request": {
          "method": "POST",
          "url": "https://claude.ai/api/...",
          "headers": [...],
          "postData": {
            "mimeType": "application/json",
            "text": "{...}"
          }
        },
        "response": {
          "status": 200,
          "statusText": "OK",
          "headers": [...],
          "content": {
            "size": 1234,
            "mimeType": "application/json",
            "text": "{...}"
          }
        },
        "startedDateTime": "2025-12-29T...",
        "time": 234
      }
    ]
  }
}
```

---

## Troubleshooting

### "No API requests found"

- Check that you're logged in
- The app might use different API patterns (try `--api-pattern` flag)
- WebSocket connections aren't in HAR - these need manual inspection

### Response bodies are empty

- Some browsers don't include large responses
- Try Firefox - it often has better HAR export
- Check if responses are compressed (look for gzip headers)

### SSE/Streaming responses are truncated

- This is expected - HAR captures the final state
- For streaming APIs, note it's SSE and document the event format manually

### Sensitive data in HAR

- HAR files contain cookies and auth tokens
- Never commit HAR files to git
- Add `*.har` to `.gitignore`

---

## Extending for New Apps

To add a new application to this workflow:

1. Identify the API base URL pattern
2. Note any special auth mechanisms
3. List the key features/endpoints to capture
4. Add a section to this document

---

## Related Files

- `scripts/api_discovery/har_parser.py` - The HAR parsing script
- `docs/claude/api-reference.md` - Claude.ai API documentation (generated)
