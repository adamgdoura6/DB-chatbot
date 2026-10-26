#!/usr/bin/env python3
"""Build data-profiler artifacts using the repository's guarded dbq entry point.

This helper deliberately has no database driver.  Every query is delegated to
``../shared/dbq.py``, which keeps the audit read-only and masks PII before the
result reaches this process.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml


AUDIT_DIR = Path(__file__).resolve().parents[3]
ROOT = AUDIT_DIR.parent
sys.path.insert(0, str(ROOT / "shared"))
import dbq  # noqa: E402

KNOWLEDGE = dbq.knowledge_dir()  # the active database's knowledge/<name>/
CATALOG = KNOWLEDGE / "_raw" / "catalog"
PROFILES = KNOWLEDGE / "_raw" / "profiles"
DBQ = ROOT / "shared" / "dbq.py"

PII_HINTS = [
    ("email", r"e_?mail"),
    ("phone", r"phone|mobile|^tel|fax"),
    ("iban", r"iban|bic|account_?number"),
    ("card", r"card_?(number|no)|^pan$"),
    ("name", r"^(first|last|full|middle|sur|given|family)_?name$|^name$|contact_?name"),
    ("address", r"street|address|addr_?line|zip|postal|postcode"),
    ("birthdate", r"birth|dob"),
    ("national_id", r"ssn|tax_?id|passport|national_?id"),
    ("ip", r"(^|_)ip(_?addr(ess)?)?$"),
    ("secret", r"password|passwd|secret|token|api_?key|hash"),
    ("health", r"diagnos|medical|health"),
]
NOT_PII = re.compile(r"(_id|_count|_type|_status|_at|_verified|_confirmed|_hash_algo)$", re.I)
MASKED_VALUE = re.compile(r"^(?:user_[0-9a-f]{6}@|<(?:email|phone|iban|card|name|address|birthdate|national_id|ip|secret|health):|<redacted>)", re.I)
NUMERIC_OR_TIME = re.compile(r"(?:smallint|integer|bigint|numeric|decimal|real|double precision|money|date|time|timestamp)", re.I)
SKIP_STATS = re.compile(r"(?:bytea|tsvector|geometry|vector)", re.I)
JSON_TYPE = re.compile(r"^(?:json|jsonb)$", re.I)
SAMPLE_TYPE = re.compile(r"(?:smallint|integer|bigint|numeric|decimal|real|double precision|money|date|time|timestamp|boolean|uuid)", re.I)


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def fqn(schema: str, table: str) -> str:
    return f"{quote_ident(schema)}.{quote_ident(table)}"


def pii_kind(column: str) -> str | None:
    if NOT_PII.search(column):
        return None
    return next((kind for kind, pattern in PII_HINTS if re.search(pattern, column, re.I)), None)


def dbq(sql: str, max_rows: int = 1000) -> tuple[dict[str, Any] | None, str | None]:
    result = subprocess.run(
        [sys.executable, str(DBQ), "--json", "--max-rows", str(max_rows), "--timeout-ms", "20000", sql],
        cwd=AUDIT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        return None, result.stderr.strip() or result.stdout.strip() or f"dbq exited {result.returncode}"
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid dbq JSON: {exc}"


def data_value_is_masked(value: object) -> bool:
    return isinstance(value, str) and bool(MASKED_VALUE.match(value))


def profile_table(table: dict[str, Any], by_table: dict[tuple[str, str], list[dict[str, Any]]]) -> tuple[str, dict[str, Any], dict[str, list[object]], set[str], set[str]]:
    schema, name = table["schema_name"], table["table_name"]
    table_key = f"{schema}.{name}"
    columns = sorted(by_table.get((schema, name), []), key=lambda column: column["position"])
    profile: dict[str, Any] = {"table": table_key, "rows": None, "sampled": False, "columns": {}, "samples": []}
    values: dict[str, list[object]] = {}
    pii_columns: set[str] = set()
    blocked_columns: set[str] = set()

    suspected_pii = {column["column_name"]: pii_kind(column["column_name"]) for column in columns}
    for column, kind in suspected_pii.items():
        if kind:
            pii_columns.add(f"{table_key}.{column}")
            if kind == "secret":
                blocked_columns.add(f"{table_key}.{column}")

    expressions = ["count(*) AS n"]
    stat_columns: list[tuple[str, dict[str, Any]]] = []
    for column in columns:
        data_type = column["data_type"] or ""
        if SKIP_STATS.search(data_type) or JSON_TYPE.search(data_type):
            continue
        ident = quote_ident(column["column_name"])
        key = f"c{column['position']}"
        expressions.extend([
            f"round(1 - count({ident})::numeric / nullif(count(*), 0), 4) AS {key}__null_frac",
            f"count(DISTINCT {ident}) AS {key}__distinct",
        ])
        if NUMERIC_OR_TIME.search(data_type):
            expressions.extend([f"min({ident})::text AS {key}__min", f"max({ident})::text AS {key}__max"])
        stat_columns.append((key, column))

    stats, error = dbq(f"SELECT {', '.join(expressions)} FROM {fqn(schema, name)}", 10)
    if error or not stats or not stats.get("rows"):
        profile["profile_error"] = error or "no result returned"
        return table_key, profile, values, pii_columns, blocked_columns

    result = stats["rows"][0]
    profile["rows"] = result.get("n", 0)
    for key, column in stat_columns:
        name = column["column_name"]
        column_profile: dict[str, Any] = {
            "null_pct": float(result.get(f"{key}__null_frac") or 0) * 100,
            "distinct": result.get(f"{key}__distinct"),
        }
        if f"{key}__min" in result:
            column_profile["min"] = result.get(f"{key}__min")
            column_profile["max"] = result.get(f"{key}__max")
        kind = suspected_pii.get(name)
        if kind:
            column_profile["pii"] = kind
        profile["columns"][name] = column_profile

    freshness_name = next((candidate for candidate in ("updated_at", "modified_at", "created_at", "inserted_at")
                           if candidate in profile["columns"]), None)
    if freshness_name:
        fresh, fresh_error = dbq(
            f"SELECT max({quote_ident(freshness_name)})::text AS freshest FROM {fqn(schema, name)}", 10
        )
        if not fresh_error and fresh and fresh.get("rows"):
            profile["freshness"] = {"column": freshness_name, "max": fresh["rows"][0].get("freshest")}

    for _, column in stat_columns:
        column_name = column["column_name"]
        column_profile = profile["columns"][column_name]
        data_type = column["data_type"] or ""
        distinct = column_profile.get("distinct")
        if column_profile.get("pii") or JSON_TYPE.search(data_type) or distinct is None or distinct > 200:
            continue
        top, top_error = dbq(
            f"SELECT {quote_ident(column_name)}::text AS value, count(*) AS n "
            f"FROM {fqn(schema, name)} WHERE {quote_ident(column_name)} IS NOT NULL "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 200",
            200,
        )
        if top_error or not top:
            continue
        top_rows = top.get("rows", [])
        column_profile["top"] = [[row.get("value"), row.get("n")] for row in top_rows]
        if any(data_value_is_masked(row.get("value")) for row in top_rows):
            column_profile["pii"] = "detected"
            pii_columns.add(f"{table_key}.{column_name}")
            continue
        if data_type.lower().startswith(("character", "text", "citext", "varchar")):
            values[f"{table_key}.{column_name}"] = [row.get("value") for row in top_rows]

    for column in columns:
        data_type = column["data_type"] or ""
        column_name = column["column_name"]
        if JSON_TYPE.search(data_type):
            keys, keys_error = dbq(
                f"SELECT DISTINCT jsonb_object_keys({quote_ident(column_name)}::jsonb) AS json_key "
                f"FROM {fqn(schema, name)} WHERE jsonb_typeof({quote_ident(column_name)}::jsonb) = 'object' LIMIT 100",
                100,
            )
            if not keys_error and keys:
                profile["columns"].setdefault(column_name, {})["json_keys"] = [
                    row.get("json_key") for row in keys.get("rows", [])
                ]

    sample_columns = [
        quote_ident(column["column_name"]) for column in columns
        if SAMPLE_TYPE.search(column["data_type"] or "") and not suspected_pii.get(column["column_name"])
    ]
    if sample_columns:
        samples, samples_error = dbq(f"SELECT {', '.join(sample_columns)} FROM {fqn(schema, name)} LIMIT 5", 5)
        if not samples_error and samples:
            profile["samples"] = samples.get("rows", [])
            for row in profile["samples"]:
                for column_name, value in row.items():
                    if data_value_is_masked(value):
                        profile["columns"].setdefault(column_name, {})["pii"] = "detected"
                        pii_columns.add(f"{table_key}.{column_name}")

    return table_key, profile, values, pii_columns, blocked_columns


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", action="append", default=[], help="Schema-qualified table to profile; repeatable")
    args = parser.parse_args()
    tables = json.loads((CATALOG / "tables.json").read_text(encoding="utf-8"))["rows"]
    if args.table:
        selected = set(args.table)
        tables = [table for table in tables if f"{table['schema_name']}.{table['table_name']}" in selected]
        missing = selected - {f"{table['schema_name']}.{table['table_name']}" for table in tables}
        if missing:
            parser.error(f"not in catalog: {', '.join(sorted(missing))}")
    columns = json.loads((CATALOG / "columns.json").read_text(encoding="utf-8"))["rows"]
    by_table: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for column in columns:
        by_table.setdefault((column["schema_name"], column["table_name"]), []).append(column)
    PROFILES.mkdir(parents=True, exist_ok=True)

    profile_results = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(profile_table, table, by_table) for table in tables]
        for future in as_completed(futures):
            profile_results.append(future.result())

    values_path = KNOWLEDGE / "values.yaml"
    all_values: dict[str, dict[str, list[object]]] = yaml.safe_load(values_path.read_text(encoding="utf-8")) if values_path.exists() else {}
    for table in tables:
        prefix = f"{table['schema_name']}.{table['table_name']}."
        for key in [key for key in all_values if key.startswith(prefix)]:
            del all_values[key]
    pii_columns: set[str] = set()
    blocked_columns: set[str] = set()
    for table_key, profile, values, table_pii, table_blocked in sorted(profile_results):
        (PROFILES / f"{table_key}.json").write_text(json.dumps(profile, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        for value_key, value_list in values.items():
            all_values[value_key] = {"values": value_list, "aliases": {}}
        pii_columns.update(table_pii)
        blocked_columns.update(table_blocked)

    (KNOWLEDGE / "values.yaml").write_text(
        yaml.safe_dump(dict(sorted(all_values.items())), sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    policies_path = KNOWLEDGE / "policies.yaml"
    policies = yaml.safe_load(policies_path.read_text(encoding="utf-8")) or {}
    policies["blocked_columns"] = sorted(set(policies.get("blocked_columns", [])) | blocked_columns)
    policies["pii_columns"] = sorted(set(policies.get("pii_columns", [])) | pii_columns)
    policies_path.write_text(yaml.safe_dump(policies, sort_keys=False, allow_unicode=True), encoding="utf-8")

    failed = sum("profile_error" in profile for _, profile, _, _, _ in profile_results)
    print(json.dumps({"profiled": len(profile_results), "failed": failed, "pii_columns": len(pii_columns),
                      "blocked_columns": len(blocked_columns), "value_indexes": len(all_values)}))


if __name__ == "__main__":
    main()
