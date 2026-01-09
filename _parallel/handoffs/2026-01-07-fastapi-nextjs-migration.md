# Handoff: FastAPI + Next.js Migration

**Date**: 2026-01-07  
**From**: Agent 1 (Backend)  
**To**: Agent 2 (Frontend)  
**Plan File**: `~/.cursor/plans/hybrid_fastapi_+_next.js_554b43ab.plan.md`

## Summary

Phase 1 (FastAPI Backend) is **COMPLETE**. The Next.js project is initialized but needs shadcn/ui setup and all page components.

## What Was Done

### Backend (COMPLETE)
- Created `src/api/` with FastAPI application
- Ported all Flask API endpoints to FastAPI
- Implemented async SSE endpoint for live updates
- Updated CLI to use uvicorn with `--reload` flag
- Added Pydantic schemas for all response types

### Frontend (PARTIAL)
- Initialized Next.js 16 + React 19 + Tailwind v4 in `web/`
- **NOT DONE**: shadcn/ui, theme, pages, components

## Files Created

```
src/api/
├── __init__.py
├── main.py           # FastAPI app with CORS
├── schemas.py        # Pydantic models
└── routes/
    ├── __init__.py
    ├── chats.py      # GET /api/chats, GET /api/chats/{id}
    ├── search.py     # GET /api/search, /api/instant-search, /api/search/facets
    └── stream.py     # GET /api/stream (SSE)
```

## Files Modified

- `requirements.txt` - Added fastapi, uvicorn, pydantic
- `src/cli/commands/web.py` - Now uses uvicorn
- `src/__main__.py` - Removed gevent monkey patching

## What Remains (13 tasks)

1. `shadcn-setup` - Install shadcn/ui
2. `port-theme` - Port CSS variables to Tailwind v4 format
3. `api-client` - Create `web/lib/api.ts`
4. `layout-component` - Header, nav, search bar
5. `page-home` - Chat list page
6. `page-database` - Table view page
7. `page-search` - Search results with facets
8. `page-chat-detail` - Chat detail with messages
9. `instant-search` - Search bar component
10. `sse-hook` - useSSE React hook
11. `markdown-component` - Markdown renderer
12. `dev-script` - Concurrent server runner
13. `cleanup` - Delete Flask code

## Quick Start for Agent 2

```bash
cd /Users/michaelhood/git/build/chatrxiv

# 1. Install Python deps
pip install -r requirements.txt

# 2. Test backend works
python -m src web --reload
# Visit http://localhost:5000/docs for Swagger UI

# 3. In another terminal, set up frontend
cd web
npm install
npx shadcn@latest init  # Choose: new-york style, zinc color
npx shadcn@latest add button input table card badge

# 4. Start frontend dev server
npm run dev
# Visit http://localhost:3000
```

## Critical Notes

1. **Tailwind v4**: Use `@theme inline` for CSS variables, OKLCH colors
2. **shadcn compatible**: Works with Tailwind v4 + React 19
3. **SSE URL changed**: `/stream` → `/api/stream`
4. **Flask still exists**: Don't delete `src/ui/web/` until frontend verified
5. **CORS configured**: For `localhost:3000` only

## Reference: Original Templates

Port UI from these Jinja templates:
- `src/ui/web/templates/base.html` → layout + globals.css
- `src/ui/web/templates/index.html` → app/page.tsx
- `src/ui/web/templates/database.html` → app/database/page.tsx
- `src/ui/web/templates/search.html` → app/search/page.tsx  
- `src/ui/web/templates/chat_detail.html` → app/chat/[id]/page.tsx
