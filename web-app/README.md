# web-app

A minimal page to talk to the database chatbot (and run the audit) from the browser.

```
frontend/   Next.js page (design: frontend/DESIGN.md)
backend/    FastAPI, laid out like the AskYourClass backend: app/{main, config, routers, models, services}
```

## Run

Two terminals:

```bash
# backend
cd web-app/backend
uv sync
uv run fastapi dev                        # http://127.0.0.1:8000

# frontend
cd web-app/frontend
npm install
npm run dev                               # http://127.0.0.1:3000  <- open this
```

The frontend forwards `/api/*` to the backend (`BACKEND_URL`, default `http://127.0.0.1:8000`).

## Chat modes

`WEBAPP_MODE` (environment of the backend):

| mode | what answers |
|---|---|
| `auto` (default) | the real agent once a database is connected (`.env`), otherwise canned replies |
| `agent` | always the real agent: Claude Code headless (`claude -p`) at the repository root |
| `simulated` | always canned replies, for working on the look |

The agent runs with an allow-list of tools (`backend/app/services/agent.py`): file read/write, subagents, and only the
shell commands the skills use (`dbq.py`, `connect.py --check`, git). All database access still goes
through `shared/dbq.py`.

## Connecting a database

Type `/connect` in the page (Supabase for now) and paste the Session pooler connection string; the page
asks for the password if the string has none. The backend (`backend/app/services/connection.py`, not the agent) runs the
same checks as `python audit-your-database/connect.py` and writes `.env` only if the connection works.
The terminal command still works too.
