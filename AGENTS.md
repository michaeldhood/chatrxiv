# AGENTS.md

## Cursor Cloud specific instructions

### Architecture

chatrxiv is a Python CLI + FastAPI backend + Next.js 16 frontend for extracting, browsing, and searching chat logs from Cursor, Claude, Claude Code, and ChatGPT. All data is stored in a local SQLite database (no external database services required).

### Running services

- **Backend (FastAPI)**: `python3 -m src web --reload` (port 5000). Serves the API and a built-in web UI. Also auto-watches for new Cursor chat data.
- **Frontend (Next.js)**: `cd web && npx next dev --webpack --port 3000`. Must use `--webpack` flag because `web/next.config.ts` has a hardcoded `turbopack.root` path from the original developer's machine that breaks Turbopack in other environments.
- **Both together**: `npm run dev` from the repo root uses `concurrently` to start both, but this also hits the Turbopack issue. Use `--webpack` when running the Next.js dev server directly.

### Key gotchas

- Use `python3` not `python` — the environment only has `python3` on PATH.
- The Next.js config (`web/next.config.ts`) has a hardcoded Turbopack root path. Always pass `--webpack` to `next dev` and `next build` in cloud environments.
- `next build --webpack` compiles successfully but has pre-existing TypeScript errors (e.g., `inline` prop in `components/markdown.tsx`). These are pre-existing, not introduced by setup.
- The `pip install` goes to `~/.local/` — ensure `~/.local/bin` is on PATH for commands like `pytest`, `uvicorn`.
- One test (`tests/test_parser.py::test_parse_chat_json_example`) fails due to a missing fixture file (`examples/chat_data_*.json`). This is a pre-existing issue.

### Commands reference

- **Tests**: `python3 -m pytest tests/` (193 pass, 1 pre-existing failure)
- **Lint**: `cd web && npx eslint` (pre-existing warnings/errors)
- **Build**: `cd web && npx next build --webpack`
- **CLI**: `python3 -m src <subcommand>` — subcommands include `ingest`, `search`, `export`, `web`, `tag`, `watch`
