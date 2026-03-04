# Multiple Chat Copy: Strategy Comparison & Recommendation

**Date:** 2026-02-16  
**Status:** Proposal  
**Branch:** `cursor/multiple-chat-copy-strategies-eda1`

---

## Problem

Today we can copy a single chat from the chat detail page (`/chat/:id`) using "Copy Chat" (markdown) or "Copy as JSON" buttons. There is no way to copy multiple chats at once. Users who want to batch-export conversations for context loading, external analysis, or archiving must open each chat individually and copy one at a time.

## Current Architecture (Relevant)

| Layer | What exists | Where |
|-------|------------|-------|
| **Frontend list** | Paginated chat list with filter (empty/non-empty) | `web/app/page.tsx` |
| **Frontend detail** | `copyChatToClipboard()` and `copyChatAsJson()` on single chat | `web/app/chat/[id]/page.tsx` |
| **API list** | `GET /api/chats?page=&limit=&filter=` returns `ChatSummary[]` (no messages) | `src/api/routes/chats.py` |
| **API detail** | `GET /api/chats/:id` returns `ChatDetail` with full messages | `src/api/routes/chats.py` |
| **DB repo** | `ChatRepository.get(chat_id)` fetches one chat + messages | `src/core/db/repositories/chat.py` |
| **Exporter** | `ChatExporter.export_chat_markdown()` writes one chat to disk | `src/services/exporter.py` |

Key constraint: the list endpoint returns summaries (no message text). Getting copyable content requires fetching each chat individually or adding a new bulk endpoint.

---

## Strategy 1: Checkbox Selection from List View

### Concept

Add a selection mechanism directly to the chat list page. Users check boxes next to the chats they want, then click a "Copy Selected" action button that appears in a floating toolbar.

### UX Flow

1. User toggles a "Select Mode" button (or long-presses / shift-clicks a chat row).
2. Checkboxes appear on each chat row.
3. User checks the chats they want (supports shift-click for range selection).
4. A sticky bottom bar appears: **"3 chats selected — Copy as Markdown | Copy as JSON | Cancel"**
5. On click, the frontend fetches full details for each selected chat in parallel, formats them, concatenates, and writes to clipboard.
6. Toast notification: "Copied 3 chats (12,450 chars)"

### Technical Changes

| Layer | Change |
|-------|--------|
| **Frontend** | Add `selectedChats: Set<number>` state to `page.tsx`, render checkboxes, add sticky action bar component |
| **API** | New `POST /api/chats/bulk` endpoint accepting `{ chat_ids: number[] }` returning `ChatDetail[]` (avoids N+1 fetches) |
| **DB** | New `ChatRepository.get_bulk(chat_ids: List[int])` method that batch-fetches chats + messages in 2 queries instead of N |
| **Frontend** | New `fetchChatsBulk(ids: number[])` API client function |
| **Shared** | Extract copy-formatting logic from `chat/[id]/page.tsx` into a shared `lib/copy.ts` utility |

### Pros

- **Precise control** -- user picks exactly the chats they want.
- **Familiar pattern** -- checkbox selection is ubiquitous (Gmail, file managers, etc.). Zero learning curve.
- **Works across pages** -- selected state can persist across pagination (store IDs in state, not index).
- **Composable** -- "Select All on Page" + "Select All Matching Filter" are natural extensions.
- **Low risk** -- individual chat fetch is already proven; bulk endpoint is a straightforward batch wrapper.

### Cons

- **UI complexity** -- checkbox mode adds visual noise; needs a toggle or smart activation (e.g., only show on hover, or require explicit "select mode").
- **Clipboard limits** -- copying 50+ large chats could hit browser clipboard size limits (~16MB in most browsers, but varies).
- **N+1 without bulk endpoint** -- if we skip the bulk API and fetch individually, copying 20 chats means 20 HTTP requests.
- **Cross-page selection** -- if user wants chats from page 1 and page 3, we need to persist selection across pagination.

### Estimated Effort

- Backend (bulk endpoint + DB method): ~2 hours
- Frontend (selection UI + action bar + copy logic extraction): ~4 hours
- **Total: ~6 hours**

---

## Strategy 2: Filter-Based Bulk Copy from List/Search View

### Concept

Add a "Copy All" button to the list view and search results that copies every chat matching the current filter criteria. The user controls what gets copied by narrowing filters (empty/non-empty, search query, tags, workspace) rather than manually selecting individual chats.

### UX Flow

1. User applies filters on the list page (e.g., filter: non-empty) or runs a search query.
2. A "Copy All Results" dropdown appears in the toolbar showing: **"Copy all 47 matching chats as Markdown | JSON"**
3. User clicks, sees a progress indicator ("Fetching 47 chats...").
4. All matching chats are fetched server-side, formatted, and returned as a single payload.
5. Frontend writes to clipboard. Toast: "Copied 47 chats (89,200 chars)"

### Technical Changes

| Layer | Change |
|-------|--------|
| **API** | New `POST /api/chats/copy` endpoint accepting filter params (same as list: `filter`, `search_query`, `tags[]`, `workspace_ids[]`) returning pre-formatted text |
| **Backend** | New `BulkCopyService` that takes filter criteria, queries matching chats, fetches messages, and formats as markdown or JSON server-side |
| **DB** | New `ChatRepository.get_all_matching(filters)` method that returns full chat+messages for all matches |
| **Frontend** | Add "Copy All Results" button to list view and search page, with loading state |
| **Shared** | Move formatting logic to backend (Python) since server does the heavy lifting |

### Pros

- **Minimal UI change** -- one button, no checkboxes, no selection state management.
- **Scales better for large batches** -- server-side formatting avoids N individual API calls.
- **Leverages existing filters** -- users already filter by empty/non-empty, search, tags, workspace. This just adds an action to the results.
- **Consistent with export paradigm** -- similar to "Export filtered data as CSV" patterns in data tools.

### Cons

- **Imprecise** -- you get ALL matching results. If you want 5 out of 47, you can't exclude the other 42 without changing filters.
- **Server load** -- formatting 100+ chats with messages server-side could be expensive (memory + CPU). Needs pagination or streaming for large sets.
- **Harder to preview** -- user doesn't see exactly what they're copying until it's on the clipboard.
- **Filter coupling** -- the copy feature becomes dependent on the filter/search infrastructure. Changes to filtering affect copy behavior.
- **Less intuitive for small batches** -- if you just want 3 specific chats, filtering down to exactly those 3 is awkward.

### Estimated Effort

- Backend (new endpoint + service + DB method): ~4 hours
- Frontend (button + loading state): ~2 hours  
- **Total: ~6 hours**

---

## Side-by-Side Comparison

| Dimension | Strategy 1: Checkbox Selection | Strategy 2: Filter-Based Bulk |
|-----------|-------------------------------|-------------------------------|
| **Precision** | Exact -- user picks individual chats | Approximate -- all-or-nothing per filter |
| **UI complexity** | Higher (checkboxes, action bar, selection state) | Lower (one button) |
| **Backend complexity** | Lower (batch fetch by IDs) | Higher (filter-to-full-fetch pipeline) |
| **Best for small batches** | Excellent | Awkward |
| **Best for large batches** | Good (with "Select All") | Excellent |
| **Clipboard risk** | Same | Same |
| **Extensibility** | Natural path to bulk delete, bulk tag, bulk export | Mostly copy-specific |
| **Effort** | ~6 hours | ~6 hours |

---

## Recommendation: Strategy 1 (Checkbox Selection)

**Strategy 1 is the stronger choice**, and here's why:

### 1. Selection infrastructure is a platform investment

Checkbox selection isn't just about copying. Once you have a selection mechanism on the list, you get bulk **tag**, bulk **delete**, bulk **export to file**, and bulk **summarize** essentially for free. Each new bulk action is just a new button in the action bar. Strategy 2 gives you bulk copy and nothing else without significant rework.

### 2. Precision matters more than convenience

In practice, users rarely want "all 47 chats matching this filter." They want "these 5 specific conversations from last week." Strategy 1 handles both cases (select 5 individually, or "Select All" for the full set). Strategy 2 only handles the latter well.

### 3. The bulk API endpoint is simpler and more reusable

`POST /api/chats/bulk { chat_ids: [1, 5, 12] }` is a clean, predictable endpoint. It does one thing: fetch N chats by ID. Strategy 2's endpoint needs to replicate the entire filter/search query parser server-side for the copy context, which is fragile coupling.

### 4. Users already know how checkboxes work

There's zero learning curve. Gmail, Finder, Windows Explorer -- everyone already has muscle memory for "check, check, check, action."

### Implementation Order

1. **Extract copy formatting** into `web/lib/copy.ts` (decouple from detail page)
2. **Add `POST /api/chats/bulk`** backend endpoint + `ChatRepository.get_bulk()`
3. **Add selection state** to list page (`selectedChats: Set<number>`)
4. **Add checkbox UI** with shift-click range selection
5. **Add floating action bar** with Copy Markdown / Copy JSON buttons
6. **Add "Select All on Page"** convenience toggle

### Future Extensions (unlocked by selection infra)

- Bulk tagging
- Bulk delete
- Bulk export to file (markdown directory, zip)
- Bulk summarize via Claude API
- "Select All Matching Filter" (combines Strategy 2's strength into Strategy 1's framework)
