#!/usr/bin/env python3
"""dbq - the only way agents touch the customer database.

Every skill runs SQL through this script, so safety does not depend on which agent
(Claude, Copilot, Codex, ...) follows the instructions:

  * read-only transaction + statement_timeout + row cap      (database level)
  * one statement only; SELECT / WITH / EXPLAIN / SHOW only    (parser level)
  * blocked columns rejected, mandatory + tenant filters injected from knowledge/policies.yaml
  * PII masked in every output (column-name hints, value patterns, policies) before an LLM sees it

Usage:
  python tools/dbq.py "SELECT ..."                 # table output
  python tools/dbq.py --json "SELECT ..."          # JSON output
  python tools/dbq.py --file query.sql
  python tools/dbq.py --cost "SELECT ..."          # EXPLAIN cost only, does not run the query
  python tools/dbq.py --check "SELECT ..."         # print the guarded SQL, do not run it

Connection: DBCHAT_DATABASE_URL (environment or .env). Optional DBCHAT_TENANT.
Exit codes: 0 ok, 2 rejected by guard, 3 database error, 4 configuration error.
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

ROOT = Path(__file__).resolve().parent.parent
POLICIES = ROOT / "knowledge" / "policies.yaml"
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


# ---------------------------------------------------------------- policies


def load_policies() -> dict:
    if not POLICIES.exists():
        return {}
    try:
        import yaml
    except ImportError:
        sys.exit("dbq: knowledge/policies.yaml exists but PyYAML is not installed (pip install pyyaml)")
    return yaml.safe_load(POLICIES.read_text(encoding="utf-8")) or {}


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
            raise Rejected("policies require filter injection: pip install sqlglot")
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


def database_url() -> str:
    url = os.getenv("DBCHAT_DATABASE_URL")
    env = ROOT / ".env"
    if not url and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DBCHAT_DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not url:
        print("dbq: DBCHAT_DATABASE_URL is not set (environment or .env)", file=sys.stderr)
        sys.exit(4)
    return url


def run(sql: str, max_rows: int, timeout_ms: int) -> tuple[list[str], list[tuple], bool]:
    try:
        import psycopg
    except ImportError:
        print("dbq: pip install 'psycopg[binary]'", file=sys.stderr)
        sys.exit(4)
    try:
        with psycopg.connect(database_url(), autocommit=False) as conn:
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
    a = ap.parse_args()

    sql = Path(a.file).read_text(encoding="utf-8") if a.file else (sys.stdin.read() if a.sql in (None, "-") else a.sql)
    policies = load_policies()
    try:
        guarded = guard(sql, policies, os.getenv("DBCHAT_TENANT"))
    except Rejected as e:
        print(f"dbq: REJECTED: {e}", file=sys.stderr)
        sys.exit(2)
    if a.check:
        print(guarded)
        return
    max_rows = max(1, min(a.max_rows or int(policies.get("max_rows", 200)), HARD_MAX_ROWS))

    if a.cost:
        _, rows, _ = run(f"EXPLAIN (FORMAT JSON) {guarded}", 1, 5000)
        plan = rows[0][0]
        plan = json.loads(plan) if isinstance(plan, str) else plan
        cost = plan[0]["Plan"]["Total Cost"]
        limit = policies.get("max_plan_cost")
        print(json.dumps({"total_cost": cost, "max_plan_cost": limit, "ok": limit is None or cost <= limit}))
        return

    limit = policies.get("max_plan_cost")
    if limit and not re.match(r"^\s*(explain|show)\b", guarded, re.I):
        _, plan_rows, _ = run(f"EXPLAIN (FORMAT JSON) {guarded}", 1, 5000)
        plan = plan_rows[0][0]
        cost = (json.loads(plan) if isinstance(plan, str) else plan)[0]["Plan"]["Total Cost"]
        if cost > limit:
            print(f"dbq: REJECTED: query plan cost {cost:,.0f} exceeds max_plan_cost {limit:,.0f}; "
                  "filter on indexed columns, narrow the time range, or aggregate less", file=sys.stderr)
            sys.exit(2)

    cols, rows, truncated = run(guarded, max_rows, min(a.timeout_ms, int(policies.get("statement_timeout_ms", 60000))))
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
