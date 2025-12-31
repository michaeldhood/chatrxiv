# API Discovery Scripts

Tools for reverse-engineering internal web application APIs by capturing and analyzing browser network traffic.

## Quick Start

```bash
# 1. Export HAR from browser DevTools (see process below)
# 2. Run the parser
python scripts/api_discovery/har_parser.py my_export.har \
    --app-name "Claude.ai" \
    --output docs/claude/api-reference.md \
    --verbose
```

## The HAR Export Process

1. Open target web app while logged in
2. Open DevTools → Network tab  
3. Check "Preserve log"
4. Use the app (navigate, click, send messages, etc.)
5. Right-click in Network tab → "Save all as HAR with content"
6. Run parser on the HAR file

## Files

| File | Purpose |
|------|---------|
| `har_parser.py` | Main script - parses HAR files, generates markdown docs |
| `README.md` | This file |

## Supported Applications

The parser works with any web application. Known-good patterns:

| App | API Patterns |
|-----|--------------|
| Claude.ai | `/api/`, `a-api.anthropic.com` |
| ChatGPT | `/backend-api/`, `/api/` |
| Notion | `/api/v3/` |

## Output

The parser generates markdown documentation with:

- Endpoint patterns (with UUIDs replaced by `{ID}`)
- HTTP methods
- Query parameters
- Request bodies (for POST/PUT/PATCH)
- Response examples
- Request counts per endpoint

## Security Note

⚠️ HAR files contain session cookies and auth tokens. Never commit them to git.

Add to `.gitignore`:
```
*.har
```
