#!/usr/bin/env python3
"""connect - connect the audit to your database, then check that the connection is safe.

Usage:
  python connect.py              # interactive: pick your provider, enter the connection, test it
  python connect.py --list       # supported and planned providers
  python connect.py --check      # test the connection already configured (safe for agents to run)
  python connect.py --provider supabase --url "postgresql://..."   # non-interactive (lands in shell history)

Writes DBCHAT_PROVIDER and DBCHAT_DATABASE_URL to the .env at the repository root. Every check runs through
shared/dbq.py, like all other database access.
Exit codes: 0 connected, 1 provider not supported yet, 3 connection failed, 4 configuration error.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ENV = ROOT / ".env"
DBQ = ROOT / "shared" / "dbq.py"
SUPPORTED_ENGINES = {"postgres"}


@dataclass
class Provider:
    label: str
    engine: str
    guide: str
    sslmode: str = "prefer"
    default_db: str = "postgres"
    hint: str = ""


PROVIDERS = {
    "supabase": Provider(
        "Supabase", "postgres", "providers/supabase.md", sslmode="require",
        hint="Dashboard > Connect > Session pooler. User is ai_reader.<project-ref>, never postgres or service_role."),
    "aws-rds-postgres": Provider(
        "AWS RDS / Aurora (PostgreSQL)", "postgres", "providers/aws.md", sslmode="require",
        hint="Use the read replica or Aurora reader endpoint if you have one. Private VPC: open a tunnel first."),
    "postgres": Provider(
        "Any other PostgreSQL (self-hosted, Neon, Google Cloud SQL, Azure, Firebase Data Connect, ...)",
        "postgres", "providers/postgres.md"),
    "firebase": Provider("Firebase / Firestore", "firestore", "providers/firebase.md"),
    "aws-rds-mysql": Provider("AWS RDS / Aurora (MySQL)", "mysql", "providers/README.md"),
    "mysql": Provider("MySQL / MariaDB / PlanetScale", "mysql", "providers/README.md"),
    "dynamodb": Provider("AWS DynamoDB", "dynamodb", "providers/README.md"),
    "snowflake": Provider("Snowflake", "snowflake", "providers/README.md"),
    "bigquery": Provider("Google BigQuery", "bigquery", "providers/README.md"),
}

IDENTITY_SQL = "SELECT current_database() AS db, current_user AS login, version() AS server_version"
PRIVILEGE_SQL = """
SELECT r.rolsuper AS superuser,
       r.rolbypassrls AS bypass_rls,
       has_database_privilege(current_user, current_database(), 'CREATE') AS can_create,
       (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
           AND n.nspname NOT LIKE 'pg_toast%'
           AND has_table_privilege(c.oid, 'INSERT, UPDATE, DELETE, TRUNCATE')) AS writable_tables,
       (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind IN ('r', 'p', 'v', 'm') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
           AND n.nspname NOT LIKE 'pg_toast%'
           AND has_table_privilege(c.oid, 'SELECT')) AS readable_tables
FROM pg_roles r WHERE r.rolname = current_user
"""


# ---------------------------------------------------------------- .env


def read_env() -> dict[str, str]:
    values = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def write_env(updates: dict[str, str]) -> None:
    """Set keys in .env, keeping every other line (comments, DBCHAT_TENANT, ...) as it is."""
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and key in updates and not line.lstrip().startswith("#"):
            lines[i] = f"{key}={updates[key]}"
            done.add(key)
    lines += [f"{k}={v}" for k, v in updates.items() if k not in done]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- connection URL


def with_sslmode(url: str, sslmode: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.setdefault("sslmode", sslmode)
    return urlunsplit(parts._replace(query=urlencode(query)))


def ask(prompt: str, default: str = "") -> str:
    try:
        value = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    except EOFError:
        sys.exit("\nconnect: no input; run this in your own terminal, or use --check / --url")
    return value or default


def prompt_url(p: Provider) -> str:
    if p.hint:
        print(f"\n{p.hint}")
    print(f"Guide: audit-your-database/{p.guide}\n")
    url = ask("Paste the connection URL, or press Enter to type host, user, ... one by one")
    if url:
        parts = urlsplit(url)
        if parts.scheme not in ("postgres", "postgresql"):
            sys.exit("connect: expected a postgresql://... URL")
        if not parts.password:
            password = getpass.getpass("Password (not shown): ")
            netloc = f"{quote(parts.username or '', safe='')}:{quote(password, safe='')}@{parts.hostname}"
            netloc += f":{parts.port}" if parts.port else ""
            url = urlunsplit(parts._replace(netloc=netloc))
        return with_sslmode(url, p.sslmode)
    host = ask("Host")
    port = ask("Port", "5432")
    database = ask("Database", p.default_db)
    user = ask("User (the read-only role)", "ai_reader")
    password = getpass.getpass("Password (not shown): ")
    url = f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}/{quote(database, safe='')}"
    return with_sslmode(url, p.sslmode)


def risky_login(url: str) -> str | None:
    user = (urlsplit(url).username or "").split(".")[0].lower()
    if user in ("postgres", "supabase_admin", "service_role", "rdsadmin", "root", "admin"):
        return f"'{user}' is an owner/admin login"
    return None


# ---------------------------------------------------------------- checks (through dbq)


def dbq(sql: str, url: str | None) -> tuple[int, dict | None, str]:
    env = dict(os.environ)
    if url:
        env["DBCHAT_DATABASE_URL"] = url
    r = subprocess.run([sys.executable, str(DBQ), "--json", "--max-rows", "5", sql],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    data = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
    return r.returncode, data, r.stderr.strip()


def inspect(url: str | None = None) -> dict:
    """Connect and check the login. Used by check() here and by the web app's backend.

    Returns {"code": dbq exit code, "error"} on failure, otherwise {"code": 0, "db", "login", "version",
    "problems": [what the login can do beyond reading], "readable_tables": int or None, "privilege_error"}.
    """
    code, ident, err = dbq(IDENTITY_SQL, url)
    if code != 0:
        return {"code": code, "error": err}
    row = ident["rows"][0]
    result = {"code": 0, "db": row["db"], "login": row["login"],
              "version": str(row["server_version"]).split(",")[0],
              "problems": [], "readable_tables": None, "privilege_error": None}

    code, priv, err = dbq(PRIVILEGE_SQL, url)
    if code != 0:
        result["privilege_error"] = err
        return result
    p = priv["rows"][0]
    result["problems"] = [label for flag, label in [
        (p["superuser"], "is a superuser"),
        (p["bypass_rls"], "bypasses row level security"),
        (p["can_create"], "can create schemas in this database"),
        (p["writable_tables"], f"can write to {p['writable_tables']} table(s)"),
    ] if flag]
    result["readable_tables"] = p["readable_tables"]
    return result


def check(provider_key: str | None, url: str | None = None) -> int:
    r = inspect(url)
    if r["code"] != 0:
        print(f"FAILED  could not connect\n        {r['error']}")
        if provider_key in PROVIDERS:
            print(f"        see audit-your-database/{PROVIDERS[provider_key].guide} (troubleshooting)")
        return r["code"]
    print(f"OK      connected to database '{r['db']}' as '{r['login']}'")
    print(f"        {r['version']}")

    if r["privilege_error"]:
        print(f"WARN    could not check privileges: {r['privilege_error']}")
        return 0
    if r["problems"]:
        print(f"WARN    this login {', '.join(r['problems'])}.")
        print("        dbq still runs every query read-only, but use a dedicated read-only role:")
        print("        audit-your-database/providers/readonly-role.sql")
    else:
        print("OK      the login is read-only")
    if not r["readable_tables"]:
        print("WARN    the login can read 0 tables: grant SELECT on the schemas to audit (readonly-role.sql)")
    else:
        print(f"OK      the login can read {r['readable_tables']} table(s) and view(s)")
    print("\nNext: open audit-your-database/ in your agent and say \"Audit my database\" (see its README).")
    return 0


# ---------------------------------------------------------------- main


def list_providers() -> None:
    for key, p in PROVIDERS.items():
        status = "supported" if p.engine in SUPPORTED_ENGINES else "planned  "
        print(f"  {status}  {key:<18} {p.label}")


def not_supported(key: str) -> int:
    p = PROVIDERS[key]
    print(f"{p.label} is not supported yet: the audit currently reads PostgreSQL catalogs only.")
    print(f"See audit-your-database/{p.guide} for what is planned and what you can do today.")
    return 1


def choose_provider() -> str:
    keys = list(PROVIDERS)
    print("Where is your database?")
    for i, key in enumerate(keys, 1):
        p = PROVIDERS[key]
        print(f"  {i}. {p.label}{'' if p.engine in SUPPORTED_ENGINES else '  (planned)'}")
    while True:
        choice = ask("Number")
        if choice.isdigit() and 1 <= int(choice) <= len(keys):
            return keys[int(choice) - 1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Connect the audit to your database.")
    ap.add_argument("--list", action="store_true", help="list providers")
    ap.add_argument("--check", action="store_true", help="test the configured connection")
    ap.add_argument("--provider", choices=PROVIDERS)
    ap.add_argument("--url", help="connection URL (prefer the interactive prompt: this lands in shell history)")
    a = ap.parse_args()

    if a.list:
        list_providers()
        return 0
    if a.check:
        return check(os.getenv("DBCHAT_PROVIDER") or read_env().get("DBCHAT_PROVIDER"))

    if a.url:
        key = a.provider or "postgres"
        if PROVIDERS[key].engine not in SUPPORTED_ENGINES:
            return not_supported(key)
        url = with_sslmode(a.url, PROVIDERS[key].sslmode)
    else:
        if not sys.stdin.isatty():
            print("connect: run this in your own terminal (it asks for the password), or use --check / --url",
                  file=sys.stderr)
            return 4
        key = a.provider or choose_provider()
        if PROVIDERS[key].engine not in SUPPORTED_ENGINES:
            return not_supported(key)
        url = prompt_url(PROVIDERS[key])

    risk = risky_login(url)
    if risk:
        print(f"\nWARN    {risk}. Create a read-only role first: audit-your-database/providers/readonly-role.sql")
        if sys.stdin.isatty() and ask("Continue anyway? (y/N)").lower() != "y":
            return 4

    print()
    code = check(key, url)
    if code == 0:
        write_env({"DBCHAT_PROVIDER": key, "DBCHAT_DATABASE_URL": url})
        print(f"Saved to {ENV} (git-ignored).")
        if os.getenv("DBCHAT_DATABASE_URL") and os.getenv("DBCHAT_DATABASE_URL") != url:
            print("WARN    DBCHAT_DATABASE_URL is also set in your environment and takes precedence over .env.")
    else:
        print("Nothing was saved.")
    return code


if __name__ == "__main__":
    sys.exit(main())
