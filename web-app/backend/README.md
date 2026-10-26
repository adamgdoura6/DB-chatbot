# web-app backend

FastAPI backend for the DB-chatbot web app: connect a database, run the audit, talk to it.

## Quick Start

```bash
cd web-app/backend

# Optional: settings of this backend (chat mode)
cp .env.example .env

# Install dependencies
uv sync

# Start development server (http://127.0.0.1:8000, docs at /docs)
uv run fastapi dev
```

The frontend (`web-app/frontend`, `npm run dev`) forwards `/api/*` here.

## Endpoints

| endpoint | what it does |
|---|---|
| `GET /api/health` | `{"ok": true}` |
| `GET /api/status` | database connected? audited? which chat answers (`agent` or `simulated`) |
| `POST /api/chat` | streams the reply, one JSON object per line |
| `POST /api/connect` | one step of `/connect`: checks the connection and writes the repository root `.env` |

## Chat modes (`WEBAPP_MODE`)

| mode | what answers |
|---|---|
| `auto` (default) | the real agent once a database is connected, otherwise canned replies |
| `agent` | always the real agent: Claude Code headless (`claude -p`) at the repository root |
| `simulated` | always canned replies, for working on the look |

Structure and rules: [`app/CLAUDE.md`](app/CLAUDE.md).
