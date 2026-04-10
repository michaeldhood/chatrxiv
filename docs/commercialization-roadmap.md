# chatrxiv Commercialization Roadmap

## Current State Assessment

### What Exists Today

chatrxiv is a **personal/developer-tool-grade** multi-source chat archive system. Here's an honest inventory:

**Strong (ship-quality for a local tool):**

- **ELT pipeline** — Extracts from Cursor, Claude.ai, ChatGPT, and Claude Code. Incremental ingestion, raw data preservation in `raw.db`, normalized domain models in `chats.db`. This is the product's core engine and it works.
- **SQLite FTS search** — Full-text search with `message_fts` and `unified_fts` virtual tables, triggers for automatic indexing, instant search and faceted search.
- **Web UI** — Next.js 16 + FastAPI backend. Browse, search (instant + faceted), read chats with rich rendering (markdown, code highlighting, tool results, terminal commands, plans). SSE live updates. Dark theme. Keyboard shortcuts. Chat outline rail. Bulk export (Markdown/JSON). Activity/cost tracking view.
- **CLI** — Click-based, modular commands for ingestion, search, export, tagging, watching, project management.
- **Tagging system** — Hierarchical, normalized, auto-tagger with language/framework/topic recognition, wildcard search.
- **Domain models** — Clean Pydantic models, repository pattern, proper schema migrations.
- **Test suite** — 20 test modules covering extractors, transformers, schemas, raw storage, database behavior, readers, tagging. Solid for the data pipeline.

**Missing (required for someone else's dollars):**

| Gap | Severity | Notes |
|-----|----------|-------|
| Authentication & user accounts | **Critical** | Zero auth. No users table, no sessions, no login. |
| Multi-tenancy / data isolation | **Critical** | Single SQLite file, single user assumed everywhere. |
| Authorization | **Critical** | Every endpoint is open. No API keys, no OAuth, no RBAC. |
| Billing / payments | **Critical** | No Stripe, no subscription model, no usage tracking for billing. |
| Deployment infrastructure | **Critical** | No Dockerfile, no docker-compose, no CI/CD, no PaaS config. |
| Database scalability | **High** | SQLite cannot handle concurrent multi-user writes. |
| API security hardening | **High** | `dangerouslySetInnerHTML` in search results, raw exception strings in error responses, no rate limiting, no request IDs. |
| Error handling (user-facing) | **High** | Most catch blocks `console.error` only. No toast notifications. `alert()` for clipboard. No loading skeletons. |
| Onboarding flow | **High** | No signup, no "connect your Cursor" wizard, no first-run experience. |
| Legal | **High** | No LICENSE file committed (MIT claimed in setup.py). No privacy policy, no ToS. |
| Frontend tests | **Medium** | Zero. No Jest, Vitest, Playwright, or Cypress. |
| API tests | **Medium** | No FastAPI TestClient usage. Only pure helper function tests. |
| CI/CD pipeline | **Medium** | No GitHub Actions workflows. |
| Observability | **Medium** | No Sentry, no structured logging, no metrics, no tracing. |
| Hardcoded config | **Medium** | `next.config.ts` has absolute path to developer machine. |
| Unused dependencies | **Low** | Radix UI packages installed but unused. |

### Product-Market Fit Hypothesis

The core value proposition is: **"Never lose context from your AI coding sessions."**

The target customer is a developer (or dev team) who uses AI coding assistants (Cursor, Claude, ChatGPT) daily and wants to:
1. Search across all their AI conversations
2. Track what they've built and how
3. Understand their AI usage costs
4. Extract patterns and knowledge from past sessions

This is a real pain point. Cursor's built-in chat history is ephemeral and unsearchable. Claude.ai and ChatGPT histories are siloed. Nobody aggregates them.

---

## The Commercialization Path

There are two viable go-to-market architectures. The choice is strategic and should be made before writing code:

### Option A: Desktop App (Electron/Tauri) — Fastest to Revenue

**Model:** One-time purchase or annual license. Data stays local. No server costs.

- Ship the existing Next.js + FastAPI as a packaged desktop app
- Auth = license key validation (simple API call on startup)
- No multi-tenancy needed (it's their machine)
- SQLite is actually perfect for this
- Billing via Gumroad, Paddle, or LemonSqueezy
- Distribution via direct download + auto-update

**Pros:** Leverages *every* existing strength. SQLite is ideal. No hosting costs. Privacy story is strong ("your data never leaves your machine"). Fast to ship.

**Cons:** Harder to do team features later. No recurring SaaS metrics for investors. Support burden for cross-platform issues.

### Option B: Cloud SaaS — Bigger Ceiling, Longer Path

**Model:** Monthly subscription. Data stored in cloud. Team features built in.

- Requires PostgreSQL migration, auth system, multi-tenancy, deployment infra
- Users connect sources via OAuth or file upload
- Hosting costs eat into margins until scale

**Pros:** Recurring revenue. Team/org features unlock higher price points. Standard SaaS metrics.

**Cons:** Needs 3-4x the infrastructure work. Privacy concerns with storing chat data in the cloud. Competitive with future features from Cursor/Anthropic themselves.

### Recommendation: Start with Option A, Design for Option B

Ship a desktop app first. Get paying customers. Use revenue to fund the cloud version. The ELT pipeline is the moat — it works regardless of deployment model.

---

## Roadmap: Desktop App to First Dollar

### Phase 0: Housekeeping (Pre-requisite)

Everything here is blocking. None of it is optional.

**0.1 — Fix broken config**
- Remove hardcoded `/Users/michaelhood/...` from `web/next.config.ts`
- Add proper `.env.example` at root
- Align `setup.py` `install_requires` with `requirements.txt`

**0.2 — Add LICENSE**
- Commit an actual MIT license file (or choose your license)

**0.3 — Remove dead dependencies**
- Remove unused Radix UI packages from `web/package.json`
- Clean up CVA if unused

**0.4 — CI/CD baseline**
- GitHub Actions: lint (ruff/eslint), test (pytest), type-check (pyright/mypy + tsc)
- Run on every PR

---

### Phase 1: Product Hardening

Make the existing tool worthy of a stranger's trust.

**1.1 — Error handling overhaul**
- Frontend: Replace `console.error` catch blocks with visible error UI (toast component or inline error regions). Remove `alert()` calls. Add `loading.tsx` route-level skeletons.
- Backend: Add global exception handler in FastAPI. Return structured error responses (error code + message, never raw exception strings). Add request ID middleware.

**1.2 — Security pass**
- Sanitize `dangerouslySetInnerHTML` usage (use DOMPurify or remove)
- Audit CORS settings for production
- Ensure no path traversal or sensitive data leakage in API responses
- Pin CORS to explicit origins only

**1.3 — API test coverage**
- Add FastAPI TestClient tests for every route
- Cover error cases, pagination edge cases, search edge cases
- Target: every endpoint has at least a happy-path and an error-path test

**1.4 — Frontend test baseline**
- Add Vitest + React Testing Library
- Test critical user flows: chat list render, search, chat detail view
- Target: core components and pages have smoke tests

---

### Phase 2: Desktop Packaging

Turn the web app into a distributable desktop application.

**2.1 — Choose packaging framework**
- **Tauri** (recommended): Rust-based, small binary, native feel, auto-update built in. The FastAPI backend runs as a sidecar process.
- Alternative: Electron (larger binary, more ecosystem support, easier Python integration via child_process).

**2.2 — Package the backend**
- Bundle Python + FastAPI as a standalone binary using PyInstaller or PyOxidizer
- Or: ship Python as a requirement and use a lightweight launcher
- SQLite databases stored in platform-appropriate app data directory

**2.3 — Package the frontend**
- Build Next.js as static export (`output: 'export'` in next.config)
- Serve from Tauri/Electron webview
- Point API calls to localhost sidecar

**2.4 — Auto-update mechanism**
- Tauri has built-in updater (Sparkle on macOS, NSIS on Windows)
- Version check against a simple API endpoint

**2.5 — Platform testing**
- macOS (primary — most Cursor users are on Mac)
- Windows
- Linux (nice to have for v1)

---

### Phase 3: Licensing & Payments

The minimum required to charge money.

**3.1 — License key system**
- On first launch: prompt for license key
- Validate against a lightweight API (LemonSqueezy/Gumroad webhook → your validation endpoint, or a simple Cloudflare Worker)
- Store validated license locally
- Graceful degradation: app works in read-only/limited mode without a key, full features with key

**3.2 — Payment integration**
- **LemonSqueezy** or **Paddle** (recommended over Stripe for desktop apps — they handle sales tax, VAT, and act as merchant of record)
- Product page with pricing
- License key delivery on purchase

**3.3 — Pricing model (suggested)**
- **$29 one-time** for personal use (v1 — maximize early adoption)
- **$49/year** subscription with updates (v2 — once there's enough value to justify recurring)
- **$99/seat/year** for teams (v3 — when team features land)

---

### Phase 4: Onboarding & First-Run Experience

The difference between "developer tool" and "product."

**4.1 — First-run wizard**
- Detect installed sources automatically (Cursor workspace storage dirs, Claude Code JSONL)
- Guide user through connecting each source
- Show progress during initial ingestion
- Celebrate: "Found 847 conversations across 3 sources!"

**4.2 — Source connection UX**
- Cursor: Auto-detect (local filesystem, no auth needed)
- Claude Code: Auto-detect (local JSONL files)
- Claude.ai: Guide through session token extraction (existing `scripts/get_claude_token.py`)
- ChatGPT: File upload for export ZIP/JSON

**4.3 — Empty states that educate**
- When no chats: explain what the app does, show how to connect sources
- When search returns nothing: suggest broadening query
- When a source has no data: explain what's needed

---

### Phase 5: Polish for Paying Customers

**5.1 — Performance**
- Lazy-load chat messages (the `GET /chats/{id}` endpoint does heavy Python post-processing — paginate or stream messages for large chats)
- Virtual scrolling for long chat lists
- Cache expensive computations (search facets, activity summaries)

**5.2 — UX refinements**
- Toast notification system (replace alerts)
- Proper keyboard navigation throughout
- Responsive layout for smaller screens (current nav breaks on mobile, but desktop app can have a minimum window size)
- Settings page: configure source paths, ingestion frequency, theme preferences

**5.3 — Marketing website**
- Simple landing page (can be a separate repo or a `/marketing` route)
- Screenshots, feature list, pricing, download button
- SEO basics

**5.4 — Documentation**
- Getting started guide
- Source connection guides (one per source)
- FAQ / troubleshooting

---

## What NOT to Build (Yet)

These are explicitly deferred. They are distractions from getting to first revenue:

- **Cloud/SaaS version** — Do this after desktop is generating revenue
- **Team collaboration features** — Single-user first
- **AI summarization as a core feature** — It exists but requires an API key; keep it as a power-user feature, not a selling point (avoids API cost liability)
- **Comical memory responses** — Fun but not a revenue driver
- **Knowledge maps / visualization** — Cool but not MVP
- **Mobile app** — Desktop-first
- **Voice commands** — No
- **Plugin system** — Premature abstraction

---

## Success Criteria

**"Ready to charge" means ALL of these are true:**

1. A stranger can download, install, and run the app without reading source code
2. The app finds their Cursor chats automatically on first launch
3. Search works reliably and quickly
4. No raw error messages or broken states are visible
5. License key gates the full experience
6. Payment flow works end-to-end (purchase → license key → activate)
7. The app doesn't crash or corrupt data
8. There's a website where someone can learn what this is and buy it

---

## Execution Order Summary

```
Phase 0: Housekeeping           ← Fix what's broken
Phase 1: Product Hardening      ← Make it trustworthy
Phase 2: Desktop Packaging      ← Make it distributable
Phase 3: Licensing & Payments   ← Make it purchasable
Phase 4: Onboarding & First-Run ← Make it usable by strangers
Phase 5: Polish                 ← Make it delightful
```

Phases 0 and 1 can run in parallel. Phases 2 and 3 can overlap. Phase 4 should be done alongside Phase 2. Phase 5 is continuous.

The critical path is: **Housekeeping → Hardening → Desktop Packaging → Licensing**. Everything else can be parallelized or deferred.
