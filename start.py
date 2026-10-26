#!/usr/bin/env python3
"""start - one command from nothing to talking to your database.

  uv run start.py

1. Connect: pick your provider, create a read-only login for the bot (the SQL is written for you), then
   paste the connection string from the page that opens in the browser.
   Several databases: pick a saved one or connect another; each gets its own knowledge/<name>/ folder.
2. Pick an agent: Claude Code, Codex, GitHub Copilot (VS Code), or the web app (in development).
3. The agent opens at the repository root. Not audited yet? It starts with "Audit my database".
   Otherwise just ask your questions.

The connection steps are the ones of audit-your-database/connect.py (same checks, same .env).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "audit-your-database"))
import connect  # noqa: E402  (audit-your-database/connect.py)

AUDIT_PROMPT = "Audit my database"


def need_requirements() -> bool:
    missing = [m for m in ("psycopg", "sqlglot", "yaml") if importlib.util.find_spec(m) is None]
    if missing:
        print(f"Missing Python packages ({', '.join(missing)}). Start it with:\n  uv run start.py")
    return bool(missing)


# ---------------------------------------------------------------- 1. connect


def migrate_legacy() -> bool:
    """A copy made before several databases were supported: move its audit under a name, once."""
    if connect.shared_dbq.active_database() or not (
            connect.read_env().get("DBCHAT_DATABASE_URL") or (ROOT / "knowledge" / "overview.md").exists()):
        return True
    print("This copy has one unnamed database. Give it a name: its audit moves to knowledge/<name>/.")
    url = connect.read_env().get("DBCHAT_DATABASE_URL", "")
    return connect.migrate(connect.ask_name(connect.suggest_name(url) if url else "main")) == 0


def choose_database() -> str | None:
    """A saved database, or None to connect a new one."""
    names = connect.shared_dbq.saved_databases()
    if not names:
        return None
    active = connect.shared_dbq.active_database()
    print("Which database?")
    for i, name in enumerate(names, 1):
        print(f"  {i}. {name}{'  (active)' if name == active else ''}{'' if connect.audited(name) else '  (not audited yet)'}")
    print(f"  {len(names) + 1}. Connect another database")
    while True:
        choice = connect.ask("Number", str(names.index(active) + 1) if active in names else "")
        if choice.isdigit() and 1 <= int(choice) <= len(names) + 1:
            return names[int(choice) - 1] if int(choice) <= len(names) else None


def connected(name: str) -> bool:
    connect.write_env({"DBCHAT_DATABASE": name})
    r = connect.inspect(connect.configured_url(name))
    if r["code"] != 0:
        print(f"The saved connection of '{name}' does not work: {r['error']}\n")
        return False
    print(f"Connected to '{name}': database '{r['db']}' as '{r['login']}'.")
    return True


def connect_database() -> str | None:
    key = connect.choose_provider()
    p = connect.PROVIDERS[key]
    if p.engine not in connect.SUPPORTED_ENGINES:
        connect.not_supported(key)
        return None
    url = connect.prompt_url(p)

    risk = connect.risky_login(url)
    if risk:
        print(f"\nWARN    {risk}. Create a read-only role first: audit-your-database/providers/readonly-role.sql")
        if connect.ask("Continue anyway? (y/N)").lower() != "y":
            return None
    print()
    name = connect.ask_name(connect.suggest_name(url))
    if connect.check(name, url) != 0:
        print("Nothing was saved.")
        return None
    connect.save(name, key, url)
    return name


# ---------------------------------------------------------------- 2. agent


AGENTS = {
    "claude": "Claude Code",
    "codex": "OpenAI Codex",
    "copilot": "GitHub Copilot (VS Code)",
    "web": "Web app (in development)",
}


def choose_agent() -> str:
    keys = list(AGENTS)
    print("\nWhich agent do you want to talk to your database with?")
    for i, key in enumerate(keys, 1):
        print(f"  {i}. {AGENTS[key]}")
    while True:
        choice = connect.ask("Number")
        if choice.isdigit() and 1 <= int(choice) <= len(keys):
            return keys[int(choice) - 1]


def require(program: str, install: str) -> str | None:
    path = shutil.which(program)
    if not path:
        print(f"'{program}' is not installed. Install it with:\n  {install}")
    return path


def run(cmd: list[str], cwd: Path = ROOT) -> int:
    # `python` in the skills must be this one, which has psycopg and sqlglot.
    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return subprocess.call(cmd, cwd=cwd, env=env)


def launch(agent: str, audited: bool) -> int:
    prompt = [] if audited else [AUDIT_PROMPT]
    if agent == "claude":
        exe = require("claude", "npm install -g @anthropic-ai/claude-code")
        return run([exe, *prompt]) if exe else 1
    if agent == "codex":
        exe = require("codex", "npm install -g @openai/codex")
        # write knowledge/ and learning/, and let dbq.py reach the database
        sandbox = ["--sandbox", "workspace-write", "-c", "sandbox_workspace_write.network_access=true"]
        return run([exe, *sandbox, *prompt]) if exe else 1
    if agent == "copilot":
        exe = require("code", "https://code.visualstudio.com, then enable the 'code' command")
        if not exe:
            return 1
        print("\nVS Code is opening. Open Copilot Chat, switch to Agent mode, and type:")
        print(f"  {AUDIT_PROMPT if not audited else 'How many customers do we have?'}")
        return run([exe, str(ROOT)])
    return launch_web()


def launch_web() -> int:
    uv = require("uv", "https://docs.astral.sh/uv/getting-started/installation/")
    npm = require("npm", "https://nodejs.org")
    if not (uv and npm):
        return 1
    frontend = ROOT / "web-app" / "frontend"
    if not (frontend / "node_modules").exists():
        run([npm, "install"], cwd=frontend)
    backend = subprocess.Popen([uv, "run", "fastapi", "dev"], cwd=ROOT / "web-app" / "backend")
    try:
        time.sleep(3)
        webbrowser.open("http://127.0.0.1:3000")
        print("\nThe web app is in development. Press Ctrl+C to stop it.")
        return run([npm, "run", "dev"], cwd=frontend)
    except KeyboardInterrupt:
        return 0
    finally:
        backend.terminate()


# ---------------------------------------------------------------- main


def main() -> int:
    if need_requirements():
        return 4
    if not sys.stdin.isatty():
        print("start: run this in your own terminal (it asks for the password)", file=sys.stderr)
        return 4

    if not migrate_legacy():
        return 4
    name = choose_database()
    if not (name and connected(name)):
        name = connect_database()
        if not name:
            return 3
    if connect.binding(name, connect.configured_url(name)) in ("mismatch", "unrecorded") and connect.bind(name) != 0:
        return 5

    audited = connect.audited(name)
    if not audited:
        print("\nThis database has not been audited yet: the agent will start with the audit.")
    return launch(choose_agent(), audited)


if __name__ == "__main__":
    sys.exit(main())
