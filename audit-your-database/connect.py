#!/usr/bin/env python3
"""connect - connect the audit to your database, then check that the connection is safe.

Usage:
  python connect.py              # interactive: pick your provider, enter the connection, test it
  python connect.py --list       # supported and planned providers
  python connect.py --databases  # the saved databases; * marks the active one
  python connect.py --use NAME   # switch the active database (no password needed)
  python connect.py --check      # test the active database's connection (safe for agents to run)
  python connect.py --bind       # record the connected database as the one knowledge/<name>/ describes
  python connect.py --migrate NAME   # move a single-database copy (knowledge/, learning/, .env) under NAME
  python connect.py --provider supabase --url "postgresql://..." --name shop   # non-interactive (shell history)

Each database has a name. Saving one writes DBCHAT_URL__<name>, DBCHAT_PROVIDER__<name> and DBCHAT_DATABASE=<name>
(the active database) to the .env at the repository root, and creates knowledge/<name>/ and learning/<name>/.
Every check runs through shared/dbq.py, like all other database access.
Exit codes: 0 connected, 1 provider not supported yet, 3 connection failed, 4 configuration error,
5 not bound (--bind needs the user's confirmation).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ENV = ROOT / ".env"
DBQ = ROOT / "shared" / "dbq.py"
sys.path.insert(0, str(DBQ.parent))
import dbq as shared_dbq  # noqa: E402  (fingerprint and knowledge/database.json live there)
SUPPORTED_ENGINES = {"postgres"}

READER = "ai_reader"  # the read-only login created by providers/readonly-role.sql
ROLE_SQL = HERE / "providers" / "readonly-role.sql"
ROLE_SQL_PASSWORD = "change-me-to-a-long-random-password"
URL_PASSWORD_PLACEHOLDERS = (":[YOUR-PASSWORD]", ":<password>")  # left in copied strings by the consoles

SUPABASE_API = "https://api.supabase.com/v1"
SUPABASE_TOKENS = "https://supabase.com/dashboard/account/tokens"

# Supabase turns on Row Level Security, which shows the read-only login zero rows without a policy
SUPABASE_RLS_SQL = """-- Supabase: let the bot read every row of the Row Level Security tables in public
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'public' AND rowsecurity LOOP
    EXECUTE format('DROP POLICY IF EXISTS ai_reader_select ON %I.%I', t.schemaname, t.tablename);
    EXECUTE format('CREATE POLICY ai_reader_select ON %I.%I FOR SELECT TO ai_reader USING (true)',
                   t.schemaname, t.tablename);
  END LOOP;
END $$;
"""


@dataclass
class Provider:
    label: str
    engine: str
    guide: str
    sslmode: str = "prefer"
    default_db: str = "postgres"
    hint: str = ""
    console: str = ""  # page with the connection string, opened before asking for it
    reader_sql: str = ""  # extra SQL for the read-only login on this provider
    stats_grant: bool = True  # the optional pg_read_all_stats grant (refused on some platforms)
    account_login: bool = False  # can set everything up through the provider's API after one login


PROVIDERS = {
    "supabase": Provider(
        "Supabase", "postgres", "providers/supabase.md", sslmode="require",
        reader_sql=SUPABASE_RLS_SQL,
        # its SQL editor runs everything in one transaction: a refused grant would undo the rest
        stats_grant=False, account_login=True),
    "aws-rds-postgres": Provider(
        "AWS RDS / Aurora (PostgreSQL)", "postgres", "providers/aws.md", sslmode="require",
        hint="Use the read replica or Aurora reader endpoint if you have one. Private VPC: open a tunnel first.",
        console="https://console.aws.amazon.com/rds/home#databases:"),
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


read_env = shared_dbq.read_env


def write_env(updates: dict[str, str], remove: tuple[str, ...] = ()) -> None:
    """Set keys in .env (and drop the `remove` ones), keeping every other line (comments, ...) as it is."""
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    done = set()
    kept = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        active = "=" in line and not line.lstrip().startswith("#")
        if active and key in remove and key not in updates:
            continue
        if active and key in updates:
            line = f"{key}={updates[key]}"
            done.add(key)
        kept.append(line)
    kept += [f"{k}={v}" for k, v in updates.items() if k not in done]
    ENV.write_text("\n".join(kept) + "\n", encoding="utf-8")


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


def copy_to_clipboard(text: str) -> bool:
    tool = {"win32": ["clip"], "darwin": ["pbcopy"]}.get(sys.platform)
    try:
        return bool(tool) and subprocess.run(tool, input=text, text=True).returncode == 0
    except OSError:
        return False


def reader_sql(p: Provider, password: str) -> str:
    """providers/readonly-role.sql with the password filled in and this provider's extra SQL."""
    lines = ROLE_SQL.read_text(encoding="utf-8").replace(ROLE_SQL_PASSWORD, password).splitlines()
    while lines and (not lines[0].strip() or lines[0].startswith("--")):  # the instructions for humans
        lines.pop(0)
    sql = "\n".join(lines) + "\n"
    head, sep, optional = sql.partition("-- Optional")  # the grant at the end, refused on some platforms
    sql = head + (p.reader_sql + "\n" if p.reader_sql else "") + (sep + optional if p.stats_grant else "")
    return sql


def create_reader(p: Provider) -> str:
    """Show the SQL that creates the read-only login; the user runs it as the owner. Returns its password."""
    password = secrets.token_urlsafe(24)  # URL-safe, so it needs no percent-encoding
    sql = reader_sql(p, password)
    print("\nThe bot gets its own login that can only read (never your owner/admin login).")
    where = "Run it as the database owner (psql, or your SQL client)."
    copied = copy_to_clipboard(sql)
    print(f"\n{sql}\n{'The SQL above is copied to your clipboard. ' if copied else ''}{where}")
    ask("Press Enter once it ran without errors")
    return password


def with_login(url: str, user: str, password: str) -> str:
    parts = urlsplit(url)
    netloc = f"{quote(user, safe='')}:{quote(password, safe='')}@{parts.hostname}"
    netloc += f":{parts.port}" if parts.port else ""
    return urlunsplit(parts._replace(netloc=netloc))


def supabase_api(token: str, method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        SUPABASE_API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "db-chatbot-connect"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Supabase API {e.code}: {e.read().decode(errors='replace')[:300]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Supabase API unreachable: {e.reason}") from None


TOKEN_HELP = f"""\
Check the token at {SUPABASE_TOKENS}:
  - it is copied completely and has not expired or been deleted;
  - it is not read-only: the setup creates a login, so the token needs write access to the database;
  - your account is an Owner or Administrator of the project's organization (other roles cannot create logins)."""


def supabase_setup(p: Provider) -> str:
    """Log in once with a Supabase access token, then create the read-only login and build its connection
    string through the Management API. The token is only used here and never saved."""
    print(f"\nLog in to Supabase once and the rest is automatic. Opening {SUPABASE_TOKENS}")
    print("Click 'Generate new token' (with write access, not read-only), give it any name, and copy it.")
    webbrowser.open(SUPABASE_TOKENS)
    while not (token := getpass.getpass("Paste the token (not shown): ").strip()):
        pass
    try:
        projects = supabase_api(token, "GET", "/projects")
        if not projects:
            sys.exit("FAILED  this Supabase account has no projects")
        if len(projects) == 1:
            project = projects[0]
        else:
            print("\nWhich project?")
            for i, x in enumerate(projects, 1):
                status = "" if x.get("status") == "ACTIVE_HEALTHY" else f"  ({x.get('status', '').lower()})"
                print(f"  {i}. {x['name']}  [{x.get('region', '')}]{status}")
            while not ((choice := ask("Number")).isdigit() and 1 <= int(choice) <= len(projects)):
                pass
            project = projects[int(choice) - 1]
        ref = project["ref"]
        print(f"\nProject {project['name']}: creating the read-only login {READER} ...")
        password = secrets.token_urlsafe(24)  # URL-safe, so it needs no percent-encoding
        supabase_api(token, "POST", f"/projects/{ref}/database/query",
                     {"query": reader_sql(p, password), "read_only": False})
        poolers = supabase_api(token, "GET", f"/projects/{ref}/config/database/pooler")
        pooler = next((c for c in poolers if c.get("database_type") == "PRIMARY"), poolers[0])
    except (RuntimeError, KeyError, IndexError) as e:
        sys.exit(f"FAILED  {e}\n\n{TOKEN_HELP}\n\nThen run this again.")
    # Session pooler: port 5432 on the pooler host (IPv4), user "<role>.<project ref>"
    url = f"postgresql://{READER}.{ref}:{password}@{pooler['db_host']}:5432/{pooler.get('db_name') or 'postgres'}"
    return with_sslmode(url, p.sslmode)


def prompt_url(p: Provider) -> str:
    if p.account_login:
        return supabase_setup(p)
    password = None
    if ask("Do you already have a read-only login for the bot? (y/N)").lower() != "y":
        password = create_reader(p)

    print()
    if p.console:
        print(f"Opening {p.console}")
        webbrowser.open(p.console)
    if p.hint:
        print(p.hint)
    print(f"Guide: audit-your-database/{p.guide}\n")
    url = ask("Paste the connection string as it is, or press Enter to type host, user, ... one by one")
    if url:
        for placeholder in URL_PASSWORD_PLACEHOLDERS:
            url = url.replace(placeholder, "")
        parts = urlsplit(url)
        if parts.scheme not in ("postgres", "postgresql"):
            sys.exit("connect: expected a postgresql://... URL")
        user = unquote(parts.username or "")
        if password and risky_login(url):
            # The console shows the owner login; use the one just created ("postgres.<ref>" -> "ai_reader.<ref>")
            user = READER + user[len(user.split(".")[0]):]
            print(f"Using the read-only login {user}.")
        password = password or (unquote(parts.password) if parts.password else None)
        password = password or getpass.getpass(f"Password of {user} (not shown): ")
        return with_sslmode(with_login(url, user, password), p.sslmode)
    host = ask("Host")
    port = ask("Port", "5432")
    database = ask("Database", p.default_db)
    user = ask("User (the read-only login)", READER)
    password = password or getpass.getpass("Password (not shown): ")
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
    # --any-database: these login checks must work before a new connection is saved or bound
    r = subprocess.run([sys.executable, str(DBQ), "--json", "--max-rows", "5", "--any-database", sql],
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


def check(name: str | None, url: str | None = None) -> int:
    provider = read_env().get(shared_dbq.provider_key(name)) if name else None
    r = inspect(url)
    if r["code"] != 0:
        print(f"FAILED  could not connect\n        {r['error']}")
        if provider in PROVIDERS:
            print(f"        see audit-your-database/{PROVIDERS[provider].guide} (troubleshooting)")
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
    problem = name and shared_dbq.mismatch(name, url or configured_url(name))
    if problem:
        print(f"WARN    {problem}.")
        print("        The agent refuses to query it. Save this database under its own name (python connect.py),")
        print("        or, if it is the same database at a new address: python connect.py --bind")
    return 0


# ---------------------------------------------------------------- several databases, one name each


LEGACY_ENV = ("DBCHAT_DATABASE_URL", "DBCHAT_PROVIDER", "DBCHAT_TENANT")  # the single-database .env keys
LEARNING_DIRS = ("traces", "proposals", "eval")


def configured_url(name: str | None = None) -> str:
    name = name or shared_dbq.active_database()
    return os.getenv("DBCHAT_DATABASE_URL") or (read_env().get(shared_dbq.url_key(name), "") if name else "")


def suggest_name(url: str) -> str:
    """A folder name for a new database: its database name, or (for the usual 'postgres') where it lives."""
    fp = shared_dbq.fingerprint(url)
    user = unquote(urlsplit(url).username or "")
    raw = fp["database"] if fp["database"] not in ("", "postgres") else (
        user.split(".", 1)[1] if "." in user else fp["host"].split(".")[0])  # Supabase pooler: login.<project-ref>
    return "".join(c if c.isalnum() or c in "_-" else "-" for c in raw.lower()).strip("-_")[:63] or "main"


def ask_name(default: str) -> str:
    while True:
        name = ask("Name for this database (its folders: knowledge/<name>/, learning/<name>/)", default)
        if shared_dbq.valid_name(name):
            return name
        print("Use lowercase letters, digits, - and _ (start with a letter or digit), "
              f"and none of {', '.join(sorted(shared_dbq.RESERVED_NAMES))}.")


def ensure_folders(name: str) -> None:
    """knowledge/<name>/ with the default policies, and learning/<name>/. Never overwrites anything."""
    knowledge = shared_dbq.knowledge_dir(name)
    knowledge.mkdir(parents=True, exist_ok=True)
    policies = knowledge / "policies.yaml"
    if not policies.exists():
        policies.write_text(shared_dbq.POLICIES_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    for sub in LEARNING_DIRS:
        (shared_dbq.learning_dir(name) / sub).mkdir(parents=True, exist_ok=True)


def save(name: str, provider: str, url: str) -> None:
    write_env({"DBCHAT_DATABASE": name, shared_dbq.url_key(name): url, shared_dbq.provider_key(name): provider})
    ensure_folders(name)


def use(name: str) -> int:
    if name not in shared_dbq.saved_databases():
        print(f"connect: no database named '{name}'. Saved: {', '.join(shared_dbq.saved_databases()) or 'none'}",
              file=sys.stderr)
        return 4
    write_env({"DBCHAT_DATABASE": name})
    print(f"OK      active database: {name} (knowledge/{name}/)")
    if os.getenv("DBCHAT_DATABASE") and os.getenv("DBCHAT_DATABASE") != name:
        print("WARN    DBCHAT_DATABASE is also set in your environment and takes precedence over .env.")
    return 0


def audited(name: str) -> bool:
    return (shared_dbq.knowledge_dir(name) / "overview.md").exists()


def list_databases() -> int:
    names, active = shared_dbq.saved_databases(), shared_dbq.active_database()
    if not names:
        print("No database saved yet: python connect.py")
    for name in names:
        fp = shared_dbq.fingerprint(read_env()[shared_dbq.url_key(name)])
        print(f"  {'*' if name == active else ' '} {name:<24} {fp['database']} on {fp['host']}"
              f"{'' if audited(name) else '  (not audited yet)'}")
    return 0


def move_into(src: Path, dst: Path) -> None:
    """Move src to dst, merging folders. Never overwrites a file: a conflict stops the move."""
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    elif src.is_dir() and dst.is_dir():
        for child in list(src.iterdir()):
            move_into(child, dst / child.name)
        src.rmdir()  # empty now
    else:
        raise FileExistsError(f"{dst.relative_to(ROOT)} already exists; move {src.relative_to(ROOT)} by hand")


def migrate(name: str) -> int:
    """Move a single-database copy (knowledge/*, learning/*, DBCHAT_DATABASE_URL in .env) under <name>."""
    if not shared_dbq.valid_name(name):
        print("connect: the name takes lowercase letters, digits, - and _", file=sys.stderr)
        return 4
    env = read_env()
    moved = []
    for root in ("knowledge", "learning"):
        base = ROOT / root
        target = base / name
        legacy = [p for p in base.iterdir() if p.is_file() or p.name in (*shared_dbq.RESERVED_NAMES, "_raw")] \
            if base.exists() else []
        try:
            for p in legacy:
                move_into(p, target / p.name)
                moved.append(f"{root}/{p.name}")
        except FileExistsError as e:
            print(f"connect: stopped: {e}", file=sys.stderr)
            return 4
    if env.get("DBCHAT_DATABASE_URL"):
        renamed = {shared_dbq.url_key(name): env["DBCHAT_DATABASE_URL"], "DBCHAT_DATABASE": name}
        if env.get("DBCHAT_PROVIDER"):
            renamed[shared_dbq.provider_key(name)] = env["DBCHAT_PROVIDER"]
        if env.get("DBCHAT_TENANT"):
            renamed[shared_dbq.tenant_key(name)] = env["DBCHAT_TENANT"]
        write_env(renamed, remove=LEGACY_ENV)
        moved.append(".env connection")
    ensure_folders(name)
    print(f"OK      moved to '{name}': {', '.join(moved) or 'nothing (already migrated)'}")
    return 0


# ---------------------------------------------------------------- which database knowledge/<name>/ describes


def binding(name: str, url: str) -> str:
    """fresh (nothing audited or recorded), match, mismatch, or unrecorded (an audit without database.json)."""
    if shared_dbq.bound_database(name) is not None:
        return "mismatch" if shared_dbq.mismatch(name, url) else "match"
    return "unrecorded" if audited(name) else "fresh"


def write_binding(name: str, url: str) -> None:
    path = shared_dbq.binding_file(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(shared_dbq.fingerprint(url), indent=2) + "\n", encoding="utf-8")


def bind(name: str | None = None) -> int:
    """Record the connected database as the one knowledge/<name>/ describes (default: the active database).

    Free for a fresh audit (the onboarding skill runs it). Replacing a different database, or claiming an
    existing audit, needs the user to confirm in their own terminal: agents cannot answer the prompt.
    """
    name = name or shared_dbq.active_database()
    url = configured_url(name)
    if not name or not url:
        print("connect: no database selected; run python connect.py first", file=sys.stderr)
        return 4
    r = inspect(url)
    if r["code"] != 0:
        print(f"FAILED  could not connect\n        {r['error']}")
        return r["code"]
    fp = shared_dbq.fingerprint(url)
    state = binding(name, url)
    if state == "match":
        print(f"OK      knowledge/{name}/ already describes '{fp['database']}' on {fp['host']}:{fp['port']}")
        return 0
    if state != "fresh":
        if state == "mismatch":
            print(f"WARN    {shared_dbq.mismatch(name, url)}.")
            question = "Is it the same database, reached at a new address? (y/N)"
        else:
            question = (f"knowledge/{name}/ has an audit but does not say of which database. "
                        f"Is it the audit of '{fp['database']}' on {fp['host']}? (y/N)")
        if not sys.stdin.isatty():
            print("connect: the user has to confirm this in their own terminal: python connect.py --bind",
                  file=sys.stderr)
            return 5
        if ask(question).lower() != "y":
            print("Nothing was changed. Save the other database under its own name: python connect.py")
            return 5
    write_binding(name, url)
    print(f"OK      knowledge/{name}/ now describes '{fp['database']}' on {fp['host']}:{fp['port']}")
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
    ap.add_argument("--databases", action="store_true", help="list the saved databases (* = active)")
    ap.add_argument("--use", metavar="NAME", help="make a saved database the active one")
    ap.add_argument("--check", action="store_true", help="test the active database's connection")
    ap.add_argument("--bind", action="store_true", help="record the connected database as the one knowledge/<name>/ describes")
    ap.add_argument("--migrate", metavar="NAME", help="move a single-database copy's knowledge/, learning/ and .env under NAME")
    ap.add_argument("--name", help="name to save a new connection under (default: asked, or derived from the URL)")
    ap.add_argument("--provider", choices=PROVIDERS)
    ap.add_argument("--url", help="connection URL (prefer the interactive prompt: this lands in shell history)")
    a = ap.parse_args()

    if a.list:
        list_providers()
        return 0
    if a.databases:
        return list_databases()
    if a.use:
        return use(a.use)
    if a.migrate:
        return migrate(a.migrate)
    if a.check:
        return check(shared_dbq.active_database())
    if a.bind:
        return bind()
    if a.name and not shared_dbq.valid_name(a.name):
        print("connect: --name takes lowercase letters, digits, - and _", file=sys.stderr)
        return 4

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
    name = a.name or (ask_name(suggest_name(url)) if sys.stdin.isatty() else suggest_name(url))
    code = check(name, url)
    if code == 0:
        save(name, key, url)
        print(f"Saved as '{name}' to {ENV} (git-ignored); it is now the active database.")
        if os.getenv("DBCHAT_DATABASE_URL") and os.getenv("DBCHAT_DATABASE_URL") != url:
            print("WARN    DBCHAT_DATABASE_URL is also set in your environment and takes precedence over .env.")
        if not audited(name):
            print("\nNext: open audit-your-database/ in your agent and say \"Audit my database\" (see its README).")
    else:
        print("Nothing was saved.")
    return code


if __name__ == "__main__":
    sys.exit(main())
