#!/usr/bin/env python3
"""dbq - the only way agents touch the customer database.

Every skill runs SQL through this script, so safety does not depend on which agent
(Claude, Copilot, Codex, ...) follows the instructions:

  * read-only transaction + statement_timeout + row cap      (database level)
  * one statement only; SELECT / WITH / EXPLAIN / SHOW only    (parser level)
  * blocked columns rejected, mandatory + tenant filters injected from knowledge/policies.yaml
  * PII masked in every output (column-name hints, value patterns, policies) before an LLM sees it

Usage:
  python shared/dbq.py "SELECT ..."                 # table output
  python shared/dbq.py --json "SELECT ..."          # JSON output
  python shared/dbq.py --file query.sql
  python shared/dbq.py --cost "SELECT ..."          # EXPLAIN cost only, does not run the query
  python shared/dbq.py --check "SELECT ..."         # print the guarded SQL, do not run it

  python shared/dbq.py --active                     # which database is active, and its folders

Several databases: each has a name, its own knowledge/<name>/ and learning/<name>/, and its connection in the
root .env (DBCHAT_URL__<name>, optional DBCHAT_TENANT__<name>). DBCHAT_DATABASE (environment or .env) picks the
active one; DBCHAT_DATABASE_URL in the environment overrides its URL. knowledge/<name>/database.json records
which database the audit describes, and dbq refuses to run against any other one (its policies and PII rules
would be the wrong ones). See connect.py --use and --bind.
Exit codes: 0 ok, 2 rejected by guard, 3 database error, 4 configuration error, 5 not the audited database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
POLICIES_TEMPLATE = ROOT / "shared" / "policies-template.yaml"
DATABASE_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}")
RESERVED_NAMES = {"domains", "tables", "traces", "proposals", "eval"}  # folders of the single-database layout
HARD_MAX_ROWS = 20000

DENY_FUNCTIONS = {
    "pg_sleep", "pg_sleep_for", "pg_sleep_until", "pg_read_file", "pg_read_binary_file", "pg_ls_dir",
    "pg_stat_file", "lo_import", "lo_export", "lo_get", "dblink", "dblink_exec", "set_config",
    "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf", "nextval", "setval",
    "pg_advisory_lock", "pg_advisory_xact_lock", "query_to_xml", "pg_switch_wal",
}
WRITE_WORDS = re.compile(
    r"\b(insert|update|delete|merge|truncate|drop|alter|create|grant|revoke|copy|vacuum|analyze|"
    r"reindex|cluster|refresh|call|do|lock|comment|security|set|reset|listen|notify|prepare|execute)\b", re.I)

# ---------------------------------------------------------------- PII masking

PII_NAME = [
    ("email", r"e_?mail"), ("phone", r"phone|mobile|^tel|fax"), ("iban", r"iban|bic|account_?number"),
    ("card", r"card_?(number|no)|^pan$"), ("name", r"^(first|last|full|middle|sur|given|family)_?name$|^name$|contact_?name"),
    ("address", r"street|address|addr_?line|zip|postal|postcode"), ("birthdate", r"birth|dob"),
    ("national_id", r"ssn|tax_?id|passport|national_?id"), ("ip", r"(^|_)ip(_?addr(ess)?)?$"),
    ("secret", r"password|passwd|secret|token|api_?key|hash"), ("health", r"diagnos|medical|health"),
]
NOT_PII = re.compile(r"(_id|_count|_type|_status|_at|_verified|_confirmed|_hash_algo)$", re.I)
PII_VALUE = [
    ("email", re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")),
    ("iban", re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9 ]{11,30}$")),
    ("phone", re.compile(r"^\+\d[\d\s().-]{6,18}$")),
    ("card", re.compile(r"^(?:\d{4}[ -]?){3}\d{1,7}$")),
]


def pii_kind_for_column(name: str, extra: set[str]) -> str | None:
    n = name.lower()
    if n in extra:
        return "pii"
    if NOT_PII.search(n):
        return None
    for kind, pat in PII_NAME:
        if re.search(pat, n):
            return kind
    return None


def mask(value, kind: str | None):
    if value is None:
        return None
    s = str(value)
    if kind is None:
        for k, pat in PII_VALUE:
            if pat.match(s.strip()):
                kind = k
                break
        else:
            return value
    digest = hashlib.sha256(s.encode()).hexdigest()[:6]
    if kind == "email":
        return f"user_{digest}@{s.split('@')[-1] if '@' in s else 'example.com'}"
    if kind == "secret":
        return "<redacted>"
    return f"<{kind}:{digest}>"


# ---------------------------------------------------------------- databases


def read_env() -> dict[str, str]:
    values = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def valid_name(name: str) -> bool:
    return bool(DATABASE_NAME.fullmatch(name)) and name not in RESERVED_NAMES


def url_key(name: str) -> str:
    return f"DBCHAT_URL__{name}"


def provider_key(name: str) -> str:
    return f"DBCHAT_PROVIDER__{name}"


def tenant_key(name: str) -> str:
    return f"DBCHAT_TENANT__{name}"


def saved_databases() -> list[str]:
    return sorted(k.removeprefix(url_key("")) for k in read_env() if k.startswith(url_key("")))


def active_database() -> str | None:
    return os.getenv("DBCHAT_DATABASE") or read_env().get("DBCHAT_DATABASE") or None


def require_active() -> str:
    name = active_database()
    if not name:
        if read_env().get("DBCHAT_DATABASE_URL") or (ROOT / "knowledge" / "overview.md").exists():
            print("dbq: this copy still has the single-database layout; the user runs "
                  "`python audit-your-database/connect.py --migrate <name>` once", file=sys.stderr)
        else:
            print("dbq: no database selected; run audit-your-database/connect.py (or connect.py --use <name>)",
                  file=sys.stderr)
        sys.exit(4)
    return name


def knowledge_dir(name: str | None = None) -> Path:
    return ROOT / "knowledge" / (name or require_active())


def learning_dir(name: str | None = None) -> Path:
    return ROOT / "learning" / (name or require_active())


def tenant(name: str) -> str | None:
    return os.getenv("DBCHAT_TENANT") or read_env().get(tenant_key(name)) or None


# ---------------------------------------------------------------- policies


def load_policies(name: str | None) -> dict:
    """The active database's policies; none without an active database (only --check can get that far)."""
    path = knowledge_dir(name) / "policies.yaml" if name else None
    if path is None or not path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        sys.exit(f"dbq: {path.relative_to(ROOT)} exists but PyYAML is not installed (uv sync)")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# ---------------------------------------------------------------- guard


class Rejected(Exception):
    pass


def guard(sql: str, policies: dict, tenant: str | None) -> str:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise Rejected("empty query")
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:
        sqlglot = None

    if sqlglot is None:
        # Fallback without a parser: conservative keyword checks, fail closed if filters must be injected.
        if ";" in sql:
            raise Rejected("only one statement is allowed")
        if not re.match(r"^\s*(select|with|explain|show|values|table)\b", sql, re.I):
            raise Rejected("only SELECT / WITH / EXPLAIN / SHOW are allowed")
        if WRITE_WORDS.search(re.sub(r"'[^']*'", "''", sql)):
            raise Rejected("write or session keyword found (install sqlglot for precise checks)")
        if policies.get("mandatory_filters") or (tenant and policies.get("tenant_column")):
            raise Rejected("policies require filter injection, but sqlglot is not installed (uv sync)")
        return sql

    if re.match(r"^\s*show\b", sql, re.I):
        return sql
    if re.match(r"^\s*explain\s*(\([^)]*\banaly[sz]e\b|analy[sz]e\b)", sql, re.I):
        raise Rejected("EXPLAIN ANALYZE executes the query; use --cost instead")
    explain = re.match(r"^\s*explain\b(\s*\([^)]*\))?", sql, re.I)
    if explain:
        prefix, body = explain.group(0), sql[explain.end():]
        return f"{prefix} {guard(body, policies, tenant)}"

    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise Rejected(f"SQL does not parse: {e}")
    if len(statements) != 1:
        raise Rejected("only one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery, exp.Values)):
        raise Rejected(f"only SELECT queries are allowed (got {tree.key.upper()})")
    forbidden = tuple(getattr(exp, n) for n in ("Insert", "Update", "Delete", "Create", "Drop", "Alter", "Command",
                                                "Merge", "TruncateTable", "Into", "Lock", "Copy", "Set")
                      if hasattr(exp, n))
    for node in tree.walk():
        if isinstance(node, forbidden):
            raise Rejected(f"forbidden construct: {node.key.upper()}")
        if isinstance(node, exp.Select) and node.args.get("locks"):
            raise Rejected("row locking is not allowed")
        if isinstance(node, exp.Func):
            fname = (node.name if isinstance(node, exp.Anonymous) else node.sql_name()).lower()
            if fname in DENY_FUNCTIONS:
                raise Rejected(f"function {fname}() is not allowed")

    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    tables = [t for t in tree.find_all(exp.Table) if t.name and (t.name not in ctes or t.db)]

    def fqn(t) -> str:
        return f"{t.db or 'public'}.{t.name}"

    referenced = {fqn(t) for t in tables}
    blocked = {b.lower() for b in policies.get("blocked_columns", [])}
    if blocked:
        blocked_by_table: dict[str, set[str]] = {}
        for b in blocked:
            tbl, _, col = b.rpartition(".")
            blocked_by_table.setdefault(tbl, set()).add(col)
        hot = {t: cols for t, cols in blocked_by_table.items() if t in referenced}
        hot_cols = set().union(*hot.values()) if hot else set()
        for col in tree.find_all(exp.Column):
            if col.name.lower() in hot_cols:
                raise Rejected(f"column {col.name} is restricted")
        for star in tree.find_all(exp.Star):
            if hot and not isinstance(star.parent, (exp.Count, exp.AggFunc)):
                raise Rejected(f"SELECT * would expose restricted columns of {sorted(hot)}; list columns explicitly")

    filters: dict = policies.get("mandatory_filters") or {}
    tenant_col = policies.get("tenant_column")
    tenant_tables = set(policies.get("tenant_tables") or [])
    for t in tables:
        name = fqn(t)
        preds = list(filters.get(name, []))
        if tenant and tenant_col and name in tenant_tables:
            preds.append(f"{tenant_col} = '{tenant.replace(chr(39), chr(39) * 2)}'")
        if preds:
            schema, table = name.split(".", 1)
            inner = exp.select("*").from_(exp.table_(table, db=schema)).where(
                " AND ".join(f"({p})" for p in preds), dialect="postgres")
            t.replace(inner.subquery(t.alias_or_name))
    return tree.sql(dialect="postgres")


# ---------------------------------------------------------------- database


def database_url(name: str | None) -> str:
    url = os.getenv("DBCHAT_DATABASE_URL") or (read_env().get(url_key(name)) if name else None)
    if not url:
        print(f"dbq: no connection saved for database '{name}'; run audit-your-database/connect.py",
              file=sys.stderr)
        sys.exit(4)
    if not url.startswith(("postgres://", "postgresql://")):
        print("dbq: only PostgreSQL databases are supported for now (Supabase, AWS RDS/Aurora Postgres, ...); "
              "see audit-your-database/providers/", file=sys.stderr)
        sys.exit(4)
    return url


def fingerprint(url: str) -> dict:
    """Which database a URL points at: host, port and database name. Never the login or the password."""
    parts = urlsplit(url)
    user = unquote(parts.username or "")
    return {"host": (parts.hostname or "localhost").lower(), "port": parts.port or 5432,
            "database": unquote(parts.path.lstrip("/")) or user}  # libpq defaults the database to the login


def binding_file(name: str) -> Path:
    return knowledge_dir(name) / "database.json"


def bound_database(name: str) -> dict | None:
    """The database knowledge/<name>/ describes, or None if the audit has not recorded one yet."""
    path = binding_file(name)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: data.get(k) for k in ("host", "port", "database")}


def mismatch(name: str, url: str) -> str | None:
    """Why this URL is not the database audited as <name>, or None if it is (or none is recorded yet)."""
    bound = bound_database(name)
    if bound is None:
        return None
    current = fingerprint(url)
    if current == bound:
        return None
    return (f"the connection points at database '{current['database']}' on {current['host']}:{current['port']}, "
            f"but knowledge/{name}/ is the audit of '{bound['database']}' on {bound['host']}:{bound['port']}")


def require_audited_database(name: str, url: str) -> None:
    problem = mismatch(name, url)
    if problem:
        print(f"dbq: REFUSED: {problem}. Its policies and PII rules do not fit this database.\n"
              "  Another database: save it under its own name (`python audit-your-database/connect.py`).\n"
              "  The same database at a new address: the user runs `python audit-your-database/connect.py --bind`"
              " in their own terminal.", file=sys.stderr)
        sys.exit(5)


def run(sql: str, url: str, max_rows: int, timeout_ms: int) -> tuple[list[str], list[tuple], bool]:
    try:
        import psycopg
    except ImportError:
        print("dbq: psycopg is not installed: run uv sync at the repository root", file=sys.stderr)
        sys.exit(4)
    try:
        with psycopg.connect(url, autocommit=False, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute("BEGIN READ ONLY")
                cur.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
                cur.execute(sql)
                cols = [d.name for d in cur.description] if cur.description else []
                rows = cur.fetchmany(max_rows + 1) if cur.description else []
            conn.rollback()
    except psycopg.Error as e:
        print(f"dbq: database error: {str(e).strip()}", file=sys.stderr)
        sys.exit(3)
    return cols, rows[:max_rows], len(rows) > max_rows


def _plain(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (bytes, memoryview)):
        return f"<{len(bytes(v))} bytes>"
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)[:500]
    return v


def main():
    ap = argparse.ArgumentParser(description="Run read-only, guarded SQL against the customer database.")
    ap.add_argument("sql", nargs="?", help="SQL text, or '-' for stdin")
    ap.add_argument("--file")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--max-rows", type=int, default=None,
                    help="default: policies max_rows (answers) or 200; catalog crawls may pass up to 20000")
    ap.add_argument("--timeout-ms", type=int, default=15000)
    ap.add_argument("--cost", action="store_true", help="only print the EXPLAIN total cost")
    ap.add_argument("--check", action="store_true", help="only print the guarded SQL")
    ap.add_argument("--active", action="store_true", help="print the active database and its folders")
    ap.add_argument("--any-database", action="store_true", help=argparse.SUPPRESS)  # connect.py's login checks only
    a = ap.parse_args()

    if a.active:
        name = require_active()
        print(f"database:  {name}\nknowledge: knowledge/{name}/\nlearning:  learning/{name}/")
        return
    sql = Path(a.file).read_text(encoding="utf-8") if a.file else (sys.stdin.read() if a.sql in (None, "-") else a.sql)
    # --check needs no database; connect.py's login checks run before a new connection has a name
    name = active_database() if a.check or a.any_database else require_active()
    policies = load_policies(name)
    try:
        guarded = guard(sql, policies, tenant(name) if name else None)
    except Rejected as e:
        print(f"dbq: REJECTED: {e}", file=sys.stderr)
        sys.exit(2)
    if a.check:
        print(guarded)
        return
    url = database_url(name)
    if name and not a.any_database:
        require_audited_database(name, url)
    max_rows = max(1, min(a.max_rows or int(policies.get("max_rows", 200)), HARD_MAX_ROWS))

    if a.cost:
        _, rows, _ = run(f"EXPLAIN (FORMAT JSON) {guarded}", url, 1, 5000)
        plan = rows[0][0]
        plan = json.loads(plan) if isinstance(plan, str) else plan
        cost = plan[0]["Plan"]["Total Cost"]
        limit = policies.get("max_plan_cost")
        print(json.dumps({"total_cost": cost, "max_plan_cost": limit, "ok": limit is None or cost <= limit}))
        return

    limit = policies.get("max_plan_cost")
    if limit and not re.match(r"^\s*(explain|show)\b", guarded, re.I):
        _, plan_rows, _ = run(f"EXPLAIN (FORMAT JSON) {guarded}", url, 1, 5000)
        plan = plan_rows[0][0]
        cost = (json.loads(plan) if isinstance(plan, str) else plan)[0]["Plan"]["Total Cost"]
        if cost > limit:
            print(f"dbq: REJECTED: query plan cost {cost:,.0f} exceeds max_plan_cost {limit:,.0f}; "
                  "filter on indexed columns, narrow the time range, or aggregate less", file=sys.stderr)
            sys.exit(2)

    cols, rows, truncated = run(guarded, url, max_rows, min(a.timeout_ms, int(policies.get("statement_timeout_ms", 60000))))
    extra = {c.split(".")[-1].lower() for c in policies.get("pii_columns", [])}
    kinds = [pii_kind_for_column(c, extra) for c in cols]
    masked = [[mask(_plain(v), k) for v, k in zip(r, kinds)] for r in rows]

    if a.json:
        print(json.dumps({"sql": guarded, "columns": cols, "rows": [dict(zip(cols, r)) for r in masked],
                          "row_count": len(masked), "truncated": truncated}, default=str, indent=1))
        return
    if not cols:
        print("(no result set)")
        return
    cells = [[("NULL" if v is None else str(v)).replace("\n", " ")[:80] for v in r] for r in masked]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(cols)]
    print(" | ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in cells:
        print(" | ".join(v.ljust(w) for v, w in zip(r, widths)))
    print(f"({len(masked)} row{'s' if len(masked) != 1 else ''}{', truncated' if truncated else ''})")
    if guarded != sql.strip().rstrip(";").strip():
        print(f"guarded sql: {guarded}", file=sys.stderr)


if __name__ == "__main__":
    main()
