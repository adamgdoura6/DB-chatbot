"""Real chat: runs Claude Code headless at the repository root for each message.

The root AGENTS.md routes the agent to the right folder, so the same chat both answers questions
(talk-to-your-database) and runs the audit (audit-your-database). All database access still goes
through shared/dbq.py: the agent may only run the commands in ALLOWED_TOOLS, everything else is denied.

A conversation is a Claude Code session; its id comes back as {"type": "conversation"} and is passed
again with the next message to resume it.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator, Optional

from app.config import settings

DETAILS = "<<details>>"
SESSION_ID = re.compile(r"[0-9a-f-]{36}")

# Read and write files (the audit writes knowledge/), delegate to subagents, and run only the
# commands the skills use. Unlisted tools are denied in headless mode.
ALLOWED_TOOLS = [
    "Read", "Glob", "Grep", "Write", "Edit", "Task", "TodoWrite",
    "Bash(python ../shared/dbq.py:*)", "Bash(python shared/dbq.py:*)",
    "Bash(python connect.py --check)", "Bash(python connect.py --list)",
    "Bash(python audit-your-database/connect.py --check)",
    "Bash(python ../audit-your-database/connect.py --check)",
    "Bash(cd:*)", "Bash(ls:*)",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git add:*)",
    "Bash(git commit:*)", "Bash(git switch:*)", "Bash(git revert:*)",
]

# How the page shows a reply: prose first, the "show your work" part separately.
SYSTEM_PROMPT = f"""\
You are talking to someone through a minimal web page, not a terminal. They see only your final reply.
Write it as short plain prose: no markdown, no headings, no lists, no code blocks.
Do not put SQL, table names or caveats in the prose. Put them at the very end, after a line containing
exactly {DETAILS}, as one JSON object: {{"sql": string or null, "tables": [string], "note": string or null}}.
"note" holds anything the person should know about how reliable the answer is (an unconfirmed guess,
who confirmed a fact). Leave out the {DETAILS} part when there is nothing to show.
The person cannot run commands. If the database is not connected, tell them to type /connect.
"""


def available() -> bool:
    return shutil.which("claude") is not None


def chat(message: str, conversation: Optional[str]) -> Iterator[dict]:
    cmd = [
        shutil.which("claude") or "claude", "-p",
        "--output-format", "stream-json", "--verbose",
        "--append-system-prompt", SYSTEM_PROMPT,
        "--allowedTools", ",".join(ALLOWED_TOOLS),
    ]
    if conversation and SESSION_ID.fullmatch(conversation):
        cmd += ["--resume", conversation]

    # `python` in the skills must be this environment's, which has psycopg and sqlglot.
    env = dict(os.environ)
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")

    proc = subprocess.Popen(
        cmd, cwd=settings.REPO_ROOT, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    try:
        proc.stdin.write(message)  # via stdin, so newlines and quotes need no escaping
        proc.stdin.close()
        result = None
        for line in proc.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "system" and event.get("subtype") == "init":
                yield {"type": "conversation", "id": event.get("session_id")}
            elif event.get("type") == "result":
                result = event
        proc.wait()

        if result is None or result.get("is_error"):
            reason = (result or {}).get("result") or proc.stderr.read().strip() or f"exit code {proc.returncode}"
            yield {"type": "error", "text": reason[-500:]}
            return
        # Only the final reply is shown; the agent's intermediate steps stay behind the breathing dot.
        yield from split_reply(result.get("result") or "")
    finally:
        if proc.poll() is None:
            proc.kill()


def split_reply(reply: str) -> Iterator[dict]:
    text, _, details = reply.partition(DETAILS)
    words = text.strip().split(" ")
    for i, word in enumerate(words):
        yield {"type": "text", "text": word + (" " if i < len(words) - 1 else "")}
        time.sleep(0.03)
    if details.strip():
        try:
            d = json.loads(details.strip())
            yield {"type": "details", "sql": d.get("sql"), "tables": d.get("tables") or [], "note": d.get("note")}
        except (json.JSONDecodeError, AttributeError):
            yield {"type": "details", "sql": None, "tables": [], "note": details.strip()}
