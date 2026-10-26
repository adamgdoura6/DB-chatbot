#!/usr/bin/env python3
"""Generate catalog-only cards for inaccessible managed security relations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


AUDIT = Path(__file__).resolve().parents[3]
ROOT = AUDIT.parent
sys.path.insert(0, str(ROOT / "shared"))
import dbq  # noqa: E402

KNOWLEDGE = dbq.knowledge_dir()  # the active database's knowledge/<name>/
TARGETS = {
    "extensions.pg_stat_statements": ("PostgreSQL statement-performance statistics view.", "one normalized statement statistic row", ["statement statistics", "query performance"], ["The read-only role cannot query this provider-managed view.", "The query text may contain sensitive application context; do not expose it."], ["query"]),
    "extensions.pg_stat_statements_info": ("PostgreSQL statement-statistics lifecycle metadata view.", "one statistics-collector metadata row", ["statement statistics metadata"], ["The read-only role cannot query this provider-managed view."], []),
    "pgsodium.decrypted_key": ("Restricted pgsodium view that can expose decrypted key material.", "one cryptographic key record", ["decrypted key", "key material"], ["Never query this view through the chatbot.", "The read-only role cannot query it."], ["raw_key", "decrypted_raw_key", "raw_key_nonce", "parent_key", "associated_data"]),
    "pgsodium.key": ("pgsodium key metadata and protected key-material configuration table.", "one cryptographic key record", ["encryption key metadata"], ["The catalog comment states raw key material is not stored, but the relation is security-sensitive.", "The read-only role cannot query it."], ["raw_key", "raw_key_nonce", "parent_key", "associated_data", "user_data"]),
    "pgsodium.mask_columns": ("pgsodium view mapping database columns to encryption/masking metadata.", "one configured database-column masking mapping", ["masked column mappings"], ["The read-only role cannot query this provider-managed view."], []),
    "pgsodium.masking_rule": ("pgsodium view exposing parsed encryption and masking rules.", "one configured encryption rule", ["encryption rules", "masking rules"], ["The read-only role cannot query this provider-managed view."], []),
    "pgsodium.valid_key": ("pgsodium view of currently valid or default key metadata.", "one valid cryptographic key record", ["active key metadata"], ["The read-only role cannot query this provider-managed view."], ["associated_data", "key_context"]),
    "supabase_migrations.schema_migrations": ("Supabase migration-history table.", "one applied Supabase migration", ["Supabase migration history"], ["Migration statements may contain operational or sensitive details.", "The read-only role cannot query this provider-managed table."], ["statements", "rollback", "idempotency_key"]),
    "vault.decrypted_secrets": ("Restricted Vault view that exposes decrypted secret values.", "one stored Vault secret", ["decrypted secrets"], ["Never query this view through the chatbot.", "The read-only role cannot query it."], ["secret", "decrypted_secret", "nonce", "key_id"]),
    "vault.secrets": ("Vault table holding encrypted secret records.", "one stored Vault secret", ["encrypted secrets", "Vault secrets"], ["Never query secret content through the chatbot.", "The read-only role cannot query it."], ["secret", "nonce", "key_id"]),
}


def meaning(name: str, table: str) -> str:
    special = {
        "query": "Normalized SQL statement text captured by the statistics extension",
        "queryid": "Identifier assigned to the normalized SQL statement",
        "calls": "Number of recorded statement executions",
        "rows": "Number of rows returned or affected by recorded statement executions",
        "dealloc": "Number of statement-statistics deallocations",
        "stats_reset": "Time the statement statistics were last reset",
        "raw_key": "Protected raw cryptographic key material",
        "decrypted_raw_key": "Decrypted cryptographic key material",
        "decrypted_secret": "Decrypted Vault secret value",
        "secret": "Encrypted or decrypted secret payload, depending on the view",
        "nonce": "Cryptographic nonce used for encryption",
        "key_context": "Cryptographic key context",
        "key_id": "Cryptographic key identifier",
        "parent_key": "Parent cryptographic key identifier",
        "version": "Migration version identifier",
        "statements": "SQL statements recorded for the migration",
        "rollback": "Rollback statements recorded for the migration",
        "idempotency_key": "Migration idempotency identifier",
        "status": "Provider-defined key status",
        "key_type": "Provider-defined cryptographic key type",
        "created": "Time the key record was created",
        "expires": "Time the key record expires",
        "created_at": "Time the record was created",
        "updated_at": "Time the record was last updated",
    }
    if name in special:
        return special[name]
    if name.endswith("_time"):
        return "Recorded statement timing statistic"
    if name.endswith(("_count", "_records", "_bytes", "_blks", "_hit", "_read", "_written", "_dirtied")):
        return "Recorded statement-resource statistic"
    return f"Provider-managed {name.replace('_', ' ')} field"


def main() -> None:
    columns = json.loads((KNOWLEDGE / "_raw" / "catalog" / "columns.json").read_text(encoding="utf-8"))["rows"]
    profiles_dir = KNOWLEDGE / "_raw" / "profiles"
    policies = yaml.safe_load((KNOWLEDGE / "policies.yaml").read_text(encoding="utf-8")) or {}
    pii = set(policies.get("pii_columns", []))
    blocked = set(policies.get("blocked_columns", []))
    by_table: dict[str, list[dict]] = {}
    for column in columns:
        table = f"{column['schema_name']}.{column['table_name']}"
        if table in TARGETS:
            by_table.setdefault(table, []).append(column)

    output = KNOWLEDGE / "tables"
    output.mkdir(exist_ok=True)
    for table, (summary, grain, synonyms, gotchas, additionally_sensitive) in TARGETS.items():
        profile_path = profiles_dir / f"{table}.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
        table_columns: dict[str, dict] = {}
        for column in sorted(by_table[table], key=lambda item: item["position"]):
            name = column["column_name"]
            card = {
                "type": column["data_type"],
                "meaning": meaning(name, table),
                "source": "llm_guess",
                "confidence": 0.35,
            }
            if name in additionally_sensitive or f"{table}.{name}" in blocked:
                card["pii"] = "secret"
            elif f"{table}.{name}" in pii:
                card["pii"] = "pii"
            table_columns[name] = card
        key_columns = []
        if table in {"pgsodium.key", "vault.secrets", "vault.decrypted_secrets", "pgsodium.decrypted_key", "pgsodium.valid_key"}:
            key_columns = ["id"]
        elif table == "supabase_migrations.schema_migrations":
            key_columns = ["version"]
        elif table == "extensions.pg_stat_statements":
            key_columns = ["queryid", "userid", "dbid"]
        stats = {"profile_error": profile.get("profile_error", "No profile was collected")}
        joins = ["pgsodium.key.parent_key = pgsodium.key.id (N:1, fk)"] if table == "pgsodium.key" else []
        card = {
            "table": table,
            "domain": "security_systems",
            "status": "unknown",
            "summary": summary,
            "grain": grain,
            "synonyms": synonyms,
            "stats": stats,
            "key_columns": key_columns,
            "joins": joins,
            "gotchas": gotchas,
            "mandatory_filters": [],
            "sensitivity": "sensitive",
            "source": "llm_guess",
            "confidence": 0.35,
            "columns": table_columns,
        }
        (output / f"{table}.yaml").write_text(yaml.safe_dump(card, sort_keys=False, allow_unicode=True, width=1000), encoding="utf-8")
    print(f"wrote {len(TARGETS)} security-system table cards")


if __name__ == "__main__":
    main()
