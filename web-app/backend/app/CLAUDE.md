# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this folder.

## Folder overview

| Folder | Purpose |
|---|---|
| `routers/` | FastAPI route handlers (thin: validate, call a service, return) |
| `models/` | Pydantic request/response schemas |
| `services/` | Business logic: the agent run, the simulated chat, connecting a database, status |
| `config.py` | App settings (env-driven, `web-app/backend/.env`) |

There is no `tables/` or `database/` here: this app owns no database. The customer database is reached
only through `shared/dbq.py` at the repository root.

---

## Rules & Constraints

### The repository rules apply

Read the root `AGENTS.md`. In particular:
- **All database access goes through `shared/dbq.py`** (directly, or via `audit-your-database/connect.py`,
  which calls it). Never open a database connection from this backend.
- **The agent never handles the database password.** Only `services/connection.py` touches it, and it
  never returns it, not even inside an error message (`hide()`).

### Two `.env` files

| file | holds | written by |
|---|---|---|
| `web-app/backend/.env` | settings of this backend (`WEBAPP_MODE`) | you |
| `.env` at the repository root | the database connection (`DBCHAT_*`) | `/connect` in the page, or `connect.py` |

### The agent's permissions

`services/agent.py` runs Claude Code headless with an allow-list (`ALLOWED_TOOLS`). Add a command there only
if a skill needs it; never allow arbitrary `Bash` or `python`.

### Chat stream format

`POST /api/chat` streams one JSON object per line (`conversation`, `text`, `details`, `error`). The page
(`web-app/frontend/app/page.tsx`) parses exactly these; change both together.

---

## Coding standards

- **All imports at the top of the file.** Never place `import` statements inside a function body or
  conditional block.
