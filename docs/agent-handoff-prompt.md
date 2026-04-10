# Agent Handoff Prompt: chatrxiv Commercialization Code Work

Copy everything below the line and use it as the prompt for a long-running agent.

---

You are working on the `chatrxiv` repository. Read `CLAUDE.md` at the repo root and `docs/commercialization-roadmap.md` for full context. Your job is to execute all code-only work from that roadmap — everything that does not require business decisions, external accounts, or physical machine testing.

Work through the tasks below in order. Each numbered section is a logical unit — commit after completing each one. Create a single feature branch for all work. Run tests after each phase to make sure nothing is broken.

Before starting any work, run the existing test suite (`python -m pytest tests/ -v`) to establish a baseline. Install dependencies first (`pip install -r requirements.txt && cd web && npm install && cd ..`).

---

## 1. Fix Hardcoded Config in `web/next.config.ts`

The file contains a hardcoded absolute path (`/Users/michaelhood/git/build/chatrxiv`) in the `turbopack.root` setting. Remove the `turbopack` config entirely — it's a developer-specific setting that shouldn't be in the repo. The resulting config should be minimal:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

export default nextConfig;
```

## 2. Add Root `.env.example`

Create a `.env.example` at the repo root documenting all environment variables the project uses. Find these by searching the codebase for `os.getenv`, `os.environ`, and `NEXT_PUBLIC_`. Include comments explaining each variable. At minimum it should include:

- `CHATRXIV_DB_PATH` — path to chats.db
- `CHATRXIV_RAW_DB_PATH` — path to raw.db (if used)
- `CHATRXIV_WATCH` — enable/disable file watching
- `CORS_ORIGINS` — allowed CORS origins
- `ANTHROPIC_API_KEY` — for AI summarization (optional)
- `NEXT_PUBLIC_API_URL` — API URL for the frontend

Mark optional vars as optional. Provide sensible defaults in comments.

## 3. Clean Up Unused Dependencies in `web/package.json`

Search `web/` for actual imports of `@radix-ui/*` and `class-variance-authority`. Remove any packages from `web/package.json` that are not actually imported anywhere in the `web/` source code. Run `cd web && npm install` after editing to update the lockfile. Make sure `npm run build` still passes after removal.

## 4. Align `setup.py` with `requirements.txt`

The `setup.py` `install_requires` only lists `pandas>=1.0.0`, while `requirements.txt` has the real dependency list. Update `setup.py` `install_requires` to include the core runtime dependencies from `requirements.txt` (not dev/test dependencies like pytest). Keep version specifiers loose (>=) in setup.py.

## 5. Add GitHub Actions CI Workflow

Create `.github/workflows/ci.yml` that runs on push and pull_request to `main`. It should:

- Use a matrix for Python 3.11 and 3.12
- Install Python dependencies from `requirements.txt`
- Run `python -m pytest tests/ -v`
- Install Node 20, run `cd web && npm install && npm run build` to verify the frontend builds
- Run `cd web && npx next lint` for frontend linting

Keep it simple and fast. Don't add type-checking yet if the codebase doesn't already pass pyright/mypy.

## 6. Add Global FastAPI Exception Handler

In `src/api/main.py`, add:

- A global exception handler that catches unhandled exceptions and returns a structured JSON response: `{"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred", "request_id": "<uuid>"}}` with status 500. Never expose raw exception messages to clients.
- Request ID middleware that generates a UUID for each request, adds it to the response headers as `X-Request-ID`, and makes it available to route handlers.
- Update existing routes in `src/api/routes/` that return raw `str(e)` in error responses to use generic messages instead. Search for patterns like `detail=f"...{str(e)}"` or `detail=str(e)` and replace with safe messages. Keep the detailed error in server-side logs using `logger.exception()`.

## 7. Security: Sanitize Frontend HTML Rendering

Search `web/` for `dangerouslySetInnerHTML`. For each usage:

- If the content is search result snippets with highlight markers, switch to a safe approach: parse the highlight markers and render as React elements (e.g., split on `<mark>`/`</mark>` and wrap in `<mark>` JSX elements).
- If the content is markdown that's already being rendered by `react-markdown`, it's fine — `react-markdown` doesn't use `dangerouslySetInnerHTML` by default.
- If there's no safe alternative, install `dompurify` and `@types/dompurify`, and sanitize before setting innerHTML.

## 8. Frontend Error Handling Overhaul

### 8a. Add a Toast Notification System

Create a lightweight toast component in `web/components/toast.tsx` using a React context provider. It should:

- Support `success`, `error`, `info` variants
- Auto-dismiss after a configurable timeout (default 5s)
- Stack multiple toasts
- Animate in/out
- Be styled consistent with the existing dark theme

Add the provider to `web/app/layout.tsx`.

### 8b. Replace `alert()` Calls

Search `web/` for `alert(`. Replace every instance with the toast system. For clipboard operations, show a success toast on copy and an error toast on failure.

### 8c. Replace Silent `console.error` Catch Blocks

Search all page and component files in `web/` for `catch` blocks that only `console.error`. Add visible error state to the UI — either:

- Set an error state variable and render an inline error message, OR
- Show an error toast

The user must always know when something failed. Don't silently swallow errors.

### 8d. Add Route-Level Loading Skeletons

Create `web/app/loading.tsx` (root loading), `web/app/chat/[id]/loading.tsx`, `web/app/search/loading.tsx`, `web/app/database/loading.tsx`, and `web/app/activity/loading.tsx`. Each should show a skeleton/shimmer UI appropriate to the page layout. Use simple CSS animations — no additional dependencies needed. Match the existing dark theme.

## 9. API Test Suite

Create `tests/test_api_routes.py` (or split into multiple files if it gets large). Use FastAPI's `TestClient` from `starlette.testclient`. 

For each route in the API:

- Test the happy path with valid parameters
- Test error cases (missing params, invalid IDs, bad input)
- Test pagination parameters where applicable
- Test that error responses have the structured format from step 6

You'll need to set up a test database fixture. Create a `tests/conftest.py` with:

- A fixture that creates a temporary `chats.db` with the proper schema
- A fixture that creates a FastAPI test client pointing at that database
- Some seed data (a few chats with messages) for tests to query against

Use dependency overrides to inject the test database:

```python
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.deps import get_db

def override_get_db():
    # return your test database instance
    ...

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)
```

Cover at minimum:
- `GET /api/chats` — list, pagination, filters
- `GET /api/chats/{id}` — valid ID, invalid ID
- `POST /api/chats/bulk` — valid IDs, empty list, too many IDs
- `GET /api/search` — valid query, empty query, short query
- `GET /api/instant-search` — valid query
- `GET /api/search/facets` — with and without query
- `GET /api/filter-options` — basic response structure
- `GET /api/health` — returns 200
- `GET /api/activity` — basic response
- `GET /api/stream` — connects and receives initial event (SSE)

## 10. Frontend Test Setup

### 10a. Install Testing Dependencies

In `web/`, install: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@vitejs/plugin-react`, `jsdom`. Add to `devDependencies`.

Add to `web/package.json` scripts:

```json
"test": "vitest",
"test:run": "vitest run"
```

Create `web/vitest.config.ts` with React plugin and jsdom environment.

### 10b. Write Smoke Tests

Create tests for the critical rendering paths. At minimum:

- `web/__tests__/components/search-bar.test.tsx` — renders, accepts input, triggers search
- `web/__tests__/components/message.test.tsx` — renders user and assistant messages
- `web/__tests__/components/markdown.test.tsx` — renders markdown content

These don't need to be exhaustive — they're a foundation others can build on. Mock `fetch` calls to the API.

## 11. Add `conftest.py` for Shared Fixtures

If one doesn't exist yet, create `tests/conftest.py` and consolidate duplicated fixtures from across test files (particularly the `temp_db` / `temp_storage` patterns that appear in multiple files). Don't break existing tests — add shared fixtures and update files to use them where it reduces duplication. Run the full test suite after to verify nothing broke.

## 12. Settings Page

Create `web/app/settings/page.tsx` — a settings page accessible from the nav. It should display:

- Current database path and size (add a `GET /api/settings` endpoint that returns this info)
- Source status: which sources are configured and their last ingestion time (available from `ingestion_state` table)
- A button to trigger manual re-ingestion (add `POST /api/ingest` endpoint that triggers the ingestion pipeline)
- Configurable source paths (Cursor workspace storage dir, Claude Code data dir, ChatGPT export path) — store these in a new `settings` table in the database or a config file

Add a "Settings" link to the nav in `web/app/layout.tsx`.

## 13. First-Run / Onboarding Detection

Add logic to detect if this is a first run (no chats in the database). 

- Add a `GET /api/status` endpoint that returns: `{ "has_data": bool, "chat_count": int, "sources": [{"name": "cursor", "configured": bool, "last_ingestion": str|null, "chat_count": int}, ...] }`
- On the frontend home page, if `has_data` is false, show an onboarding card instead of the empty chat list. The card should:
  - Welcome the user
  - Show detected sources (which ones are available on this machine)
  - Have a "Start Ingestion" button that triggers `POST /api/ingest`
  - Show progress/status during ingestion
  - Transition to the normal chat list view when done

## 14. Lazy-Load Chat Messages

The `GET /api/chats/{id}` endpoint currently returns all messages with heavy post-processing. Add pagination support:

- Add `?message_offset=0&message_limit=50` query parameters
- Return `total_messages` count in the response
- Frontend: load first 50 messages immediately, then load more as the user scrolls (infinite scroll or "Load more" button)
- Keep the existing behavior as default (no params = all messages) for backward compatibility

## 15. Final Verification

After all work is complete:

1. Run `python -m pytest tests/ -v` — all tests must pass
2. Run `cd web && npm run build` — frontend must build without errors
3. Run `cd web && npx next lint` — no lint errors
4. Run `cd web && npm test -- --run` — frontend tests must pass (if vitest is set up)
5. Start the dev server (`python -m src web`) and verify the API responds on `http://localhost:5000/api/health`

Fix any failures before considering the work complete. Commit all changes with clear, descriptive messages — one commit per logical unit of work (roughly one per numbered section above).
