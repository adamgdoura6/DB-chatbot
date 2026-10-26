#!/usr/bin/env python3
"""Derive conservative quality findings from completed audit artifacts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
import sys
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
LEGACY = re.compile(r"(?:_old|_bak|_backup|_copy|_tmp|_v2|_2023)$|^(?:tmp_|old_|test_)", re.I)
SOFT_DELETE = {"deleted_at", "is_deleted", "archived_at", "removed_at"}
TEST_MARKERS = {"is_test", "is_demo", "is_internal", "livemode"}


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)


def main() -> None:
    tables = json.loads((CATALOG / "tables.json").read_text(encoding="utf-8"))["rows"]
    columns = json.loads((CATALOG / "columns.json").read_text(encoding="utf-8"))["rows"]
    constraints = json.loads((CATALOG / "constraints.json").read_text(encoding="utf-8"))["rows"]
    joins = yaml.safe_load((KNOWLEDGE / "joins.yaml").read_text(encoding="utf-8")) or []
    profiles: dict[str, dict[str, Any]] = {}
    for path in PROFILES.glob("*.json"):
        profile = json.loads(path.read_text(encoding="utf-8"))
        profiles[profile["table"]] = profile

    findings: list[dict[str, Any]] = []
    table_names = {f"{table['schema_name']}.{table['table_name']}" for table in tables}
    columns_by_table: dict[str, set[str]] = {}
    for column in columns:
        columns_by_table.setdefault(f"{column['schema_name']}.{column['table_name']}", set()).add(column["column_name"])
    pk_tables = {f"{row['schema_name']}.{row['table_name']}" for row in constraints if row["type"] == "p"}

    newest: datetime | None = None
    freshness: dict[str, tuple[str, datetime]] = {}
    for table, profile in profiles.items():
        data = profile.get("freshness") or {}
        timestamp = parse_timestamp(data.get("max"))
        if timestamp:
            freshness[table] = (data.get("column", "timestamp"), timestamp)
            newest = max(newest, timestamp) if newest else timestamp

    for table in sorted(table_names):
        profile = profiles.get(table, {})
        table_name = table.split(".", 1)[1]
        if LEGACY.search(table_name):
            findings.append({"table": table, "kind": "legacy_name", "detail": "Name matches a legacy or temporary naming pattern.",
                             "severity": "warn", "decision": "unknown"})
        if profile.get("rows") == 0:
            findings.append({"table": table, "kind": "empty", "detail": "Exact profile count is zero.", "severity": "info"})
        if table not in pk_tables and next((t for t in tables if f"{t['schema_name']}.{t['table_name']}" == table), {}).get("kind") in {"table", "partitioned_table"}:
            findings.append({"table": table, "kind": "no_primary_key", "detail": "Catalog has no declared primary key; duplicate rows may be possible.", "severity": "warn"})
        for marker in sorted(columns_by_table.get(table, set()) & SOFT_DELETE):
            predicate = f"{marker} IS NULL" if marker != "is_deleted" else "NOT is_deleted"
            findings.append({"table": table, "kind": "soft_delete", "detail": f"{marker} is present; active-row queries should use {predicate}.", "severity": "info"})
        for marker in sorted(columns_by_table.get(table, set()) & TEST_MARKERS):
            findings.append({"table": table, "kind": "test_data", "detail": f"{marker} may distinguish test, demo, internal, or live data.", "severity": "info"})

    if newest:
        for table, (column, timestamp) in sorted(freshness.items()):
            age_days = (newest - timestamp).days
            if age_days > 180:
                findings.append({"table": table, "kind": "stale", "detail": f"{column} is {age_days} days behind the freshest profiled table.", "severity": "warn"})

    for join in joins:
        overlap = join.get("overlap")
        if overlap is not None and 0 < overlap < 0.98:
            missing_pct = round((1 - float(overlap)) * 100, 2)
            findings.append({"table": join["left"], "kind": "orphans",
                             "detail": f"{missing_pct}% of {'.'.join(join['left_columns'])} values do not match {join['right']}.",
                             "severity": "warn" if missing_pct > 2 else "info"})

    findings.sort(key=lambda item: (item["table"], item["kind"], item["detail"]))
    (KNOWLEDGE / "quality.yaml").write_text(yaml.safe_dump(findings, sort_keys=False, allow_unicode=True), encoding="utf-8")

    policies_path = KNOWLEDGE / "policies.yaml"
    policies = yaml.safe_load(policies_path.read_text(encoding="utf-8")) or {}
    mandatory = policies.get("mandatory_filters") or {}
    for finding in findings:
        if finding["kind"] != "soft_delete":
            continue
        predicate = finding["detail"].split(" should use ", 1)[1].rstrip(".")
        mandatory.setdefault(finding["table"], [])
        if predicate not in mandatory[finding["table"]]:
            mandatory[finding["table"]].append(predicate)
    policies["mandatory_filters"] = {table: sorted(predicates) for table, predicates in sorted(mandatory.items())}
    policies_path.write_text(yaml.safe_dump(policies, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(json.dumps({"findings": len(findings), "soft_delete_filters": len(policies["mandatory_filters"]),
                      "warnings": sum(item["severity"] == "warn" for item in findings)}))


if __name__ == "__main__":
    main()
