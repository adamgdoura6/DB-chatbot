"""Connecting a database from the page.

This code, not the agent, handles the password (rule 8 in the root AGENTS.md): the page sends it here,
it goes into the connection URL, the URL is checked through shared/dbq.py with the same checks as
`python connect.py`, and only a working URL is written to the repository root .env. The agent never sees it.

connect() is called once per step and says what it needs next:
  need_password  the URL has no password (or Supabase's [YOUR-PASSWORD] placeholder)
  invalid        not a postgresql:// URL
  unsupported    the provider is planned, not supported yet
  risky          an owner/admin login; call again with force=True to connect anyway
  failed         could not connect ("error" has the reason, "hint" a likely fix)
  connected      saved to .env under its name, now the active database
"""

import importlib.util
import sys
from typing import Optional
from urllib.parse import quote, urlsplit, urlunsplit

from app.config import settings

# audit-your-database/connect.py is the one place that knows providers and checks; reuse it.
_spec = importlib.util.spec_from_file_location(
    "dbchat_connect", settings.REPO_ROOT / "audit-your-database" / "connect.py")
cli = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cli  # its dataclasses look the module up while it loads
_spec.loader.exec_module(cli)

PLACEHOLDER = "[YOUR-PASSWORD]"

# From audit-your-database/providers/supabase.md, troubleshooting.
HINTS = [
    ("password authentication failed", "Check the password. On the pooler the user is ai_reader.<project-ref>."),
    ("Tenant or user not found", "Check the region in the pooler host and the project ref in the user."),
    ("could not translate host name", "Use the Session pooler connection string; the direct host is IPv6-only."),
    ("failed to resolve host", "Check the host; use the Session pooler connection string."),
    ("timeout", "The database did not answer. Check the host and port."),
]


def connect(provider: str, url: str, password: Optional[str] = None, force: bool = False,
            name: Optional[str] = None) -> dict:
    p = cli.PROVIDERS.get(provider)
    if p is None:
        return {"status": "invalid", "error": f"unknown provider {provider!r}"}
    if p.engine not in cli.SUPPORTED_ENGINES:
        return {"status": "unsupported", "provider": p.label}

    url = url.strip()
    if PLACEHOLDER in url:
        if not password:
            return {"status": "need_password"}
        url = url.replace(PLACEHOLDER, quote(password, safe=""))
    invalid = {"status": "invalid", "error": "expected a postgresql://... connection string"}
    try:
        parts = urlsplit(url)
        host, port = parts.hostname, parts.port
    except ValueError:
        return invalid
    if parts.scheme not in ("postgres", "postgresql") or not host:
        return invalid
    if not parts.password:
        if not password:
            return {"status": "need_password"}
        netloc = f"{quote(parts.username or '', safe='')}:{quote(password, safe='')}@{host}"
        netloc += f":{port}" if port else ""
        url = urlunsplit(parts._replace(netloc=netloc))
    url = cli.with_sslmode(url, p.sslmode)
    name = name or cli.suggest_name(url)
    if not cli.shared_dbq.valid_name(name):
        return {"status": "invalid", "error": "the name takes lowercase letters, digits, - and _"}

    risk = cli.risky_login(url)
    if risk and not force:
        return {"status": "risky", "reason": risk}

    r = cli.inspect(url)
    if r["code"] != 0:
        error = hide(r["error"], url)
        hint = next((h for needle, h in HINTS if needle.lower() in error.lower()), None)
        return {"status": "failed", "error": error, "hint": hint}

    cli.save(name, provider, url)
    return {
        "status": "connected", "name": name, "provider": p.label, "db": r["db"], "login": r["login"], "version": r["version"],
        "problems": r["problems"], "readable_tables": r["readable_tables"],
        "privilege_error": r["privilege_error"] and hide(r["privilege_error"], url),
    }


def hide(text: str, url: str) -> str:
    """Never send the password back, even inside an error message."""
    secret = urlsplit(url).password
    return text.replace(secret, "••••") if secret else text
