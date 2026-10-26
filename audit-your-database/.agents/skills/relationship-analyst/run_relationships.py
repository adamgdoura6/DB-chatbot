#!/usr/bin/env python3
"""Infer and verify relationship edges via the guarded dbq interface only."""

from __future__ import annotations

import json
import re
import subprocess
import sys
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
DBQ = ROOT / "shared" / "dbq.py"


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def table_sql(schema: str, table: str) -> str:
    return f"{quote_ident(schema)}.{quote_ident(table)}"


def family(data_type: str) -> str:
    data_type = (data_type or "").lower()
    if "uuid" in data_type:
        return "uuid"
    if any(token in data_type for token in ("smallint", "integer", "bigint", "numeric", "decimal", "real", "double", "serial")):
        return "number"
    if any(token in data_type for token in ("character", "text", "citext", "varchar")):
        return "text"
    return data_type


def dbq(sql: str) -> tuple[dict[str, Any] | None, str | None]:
    result = subprocess.run(
        [sys.executable, str(DBQ), "--json", "--max-rows", "10", "--timeout-ms", "20000", sql],
        cwd=AUDIT_DIR, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode:
        return None, result.stderr.strip() or result.stdout.strip() or f"dbq exited {result.returncode}"
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid dbq JSON: {exc}"


def forms(base: str) -> list[str]:
    result = [base, f"{base}s", f"{base}es"]
    if base.endswith("y"):
        result.append(f"{base[:-1]}ies")
    return result


def overlap(candidate: dict[str, Any]) -> dict[str, Any]:
    left_col, right_col = quote_ident(candidate["left_column"]), quote_ident(candidate["right_column"])
    left_table = table_sql(candidate["left_schema"], candidate["left_table"])
    right_table = table_sql(candidate["right_schema"], candidate["right_table"])
    query = (
        f"WITH l AS (SELECT DISTINCT {left_col} AS v FROM {left_table} WHERE {left_col} IS NOT NULL LIMIT 5000) "
        f"SELECT count(*) AS total, count(*) FILTER (WHERE EXISTS "
        f"(SELECT 1 FROM {right_table} r WHERE r.{right_col} = l.v)) AS hit FROM l"
    )
    result, error = dbq(query)
    if error or not result or not result.get("rows"):
        return {**candidate, "accepted": False, "error": error or "no result"}
    row = result["rows"][0]
    total, hit = int(row.get("total") or 0), int(row.get("hit") or 0)
    ratio = hit / total if total else 0.0
    return {**candidate, "total": total, "hit": hit, "overlap": ratio, "accepted": total > 0 and ratio >= 0.9}


def main() -> None:
    tables = json.loads((CATALOG / "tables.json").read_text(encoding="utf-8"))["rows"]
    columns = json.loads((CATALOG / "columns.json").read_text(encoding="utf-8"))["rows"]
    constraints = json.loads((CATALOG / "constraints.json").read_text(encoding="utf-8"))["rows"]

    table_set = {(row["schema_name"], row["table_name"]) for row in tables}
    columns_by_table: dict[tuple[str, str], list[dict[str, Any]]] = {}
    lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for column in columns:
        key = (column["schema_name"], column["table_name"])
        columns_by_table.setdefault(key, []).append(column)
        lookup[(column["schema_name"], column["table_name"], column["column_name"])] = column

    unique: set[tuple[str, str, str]] = set()
    declared: list[dict[str, Any]] = []
    for constraint in constraints:
        cols = (constraint.get("columns") or "").split(",")
        if constraint["type"] in {"p", "u"} and len(cols) == 1 and cols[0]:
            unique.add((constraint["schema_name"], constraint["table_name"], cols[0]))
        if constraint["type"] == "f":
            ref_schema, _, ref_table = (constraint.get("ref_table") or ".").partition(".")
            declared.append({
                "left": f"{constraint['schema_name']}.{constraint['table_name']}",
                "left_columns": cols,
                "right": constraint.get("ref_table"),
                "right_columns": (constraint.get("ref_columns") or "").split(","),
                "cardinality": "N:1",
                "source": "fk",
                "confidence": 1.0,
                "overlap": 1.0,
                "condition_extra": None,
            })

    by_schema_name = {(schema, name): (schema, name) for schema, name in table_set}
    candidates: list[dict[str, Any]] = []
    for (schema, left_table), left_columns in columns_by_table.items():
        for column in left_columns:
            left_column = column["column_name"]
            match = re.fullmatch(r"(.+)_id", left_column)
            if not match:
                continue
            base = match.group(1)
            targets = [by_schema_name[(schema, form)] for form in forms(base) if (schema, form) in by_schema_name]
            if not targets:
                continue
            for right_schema, right_table in targets:
                right_column = "id"
                right = lookup.get((right_schema, right_table, right_column))
                if not right or family(column["data_type"]) != family(right["data_type"]):
                    continue
                candidates.append({
                    "left_schema": schema,
                    "left_table": left_table,
                    "left_column": left_column,
                    "right_schema": right_schema,
                    "right_table": right_table,
                    "right_column": right_column,
                })

    outcomes: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(overlap, candidate) for candidate in candidates]
        for future in as_completed(futures):
            outcomes.append(future.result())
    outcomes.sort(key=lambda row: (row["left_schema"], row["left_table"], row["left_column"], row["right_table"]))

    inferred: list[dict[str, Any]] = []
    for row in outcomes:
        if not row.get("accepted"):
            continue
        left_unique = (row["left_schema"], row["left_table"], row["left_column"]) in unique
        right_unique = (row["right_schema"], row["right_table"], row["right_column"]) in unique
        cardinality = "1:1" if left_unique and right_unique else "N:1" if right_unique else "1:N" if left_unique else "N:M"
        inferred.append({
            "left": f"{row['left_schema']}.{row['left_table']}",
            "left_columns": [row["left_column"]],
            "right": f"{row['right_schema']}.{row['right_table']}",
            "right_columns": [row["right_column"]],
            "cardinality": cardinality,
            "source": "inferred",
            "confidence": round(row["overlap"] * 0.9, 3),
            "overlap": round(row["overlap"], 4),
            "condition_extra": None,
        })

    joins = sorted(declared + inferred, key=lambda edge: (edge["left"], edge["left_columns"], edge["right"]))
    (KNOWLEDGE / "joins.yaml").write_text(yaml.safe_dump(joins, sort_keys=False, allow_unicode=True), encoding="utf-8")
    raw = {"candidates": outcomes, "summary": {"declared": len(declared), "accepted": len(inferred),
                                                     "rejected": len(outcomes) - len(inferred)}}
    (KNOWLEDGE / "_raw" / "relationships.json").write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(raw["summary"]))


if __name__ == "__main__":
    main()
