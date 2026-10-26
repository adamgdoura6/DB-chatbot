#!/usr/bin/env python3
"""Create conservative catalog-only cards for an inaccessible auth schema."""

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
CATALOG = KNOWLEDGE / "_raw" / "catalog"

SUMMARIES = {
    "audit_log_entries": "Authentication audit trail entries, as described by the catalog comment.",
    "custom_oauth_providers": "Configuration records for custom OAuth providers.",
    "flow_state": "Metadata for OAuth and SSO login flows, as described by the catalog comment.",
    "identities": "Authentication identities associated with users, as described by the catalog comment.",
    "instances": "Authentication service instances or sites, as described by the catalog comment.",
    "mfa_amr_claims": "Authenticator-method-reference claims for multi-factor authentication.",
    "mfa_challenges": "Metadata about multi-factor authentication challenges.",
    "mfa_factors": "Metadata about registered multi-factor authentication factors.",
    "mfa_recovery_code_sets": "Sets used to manage multi-factor recovery codes.",
    "mfa_recovery_codes": "Individual multi-factor recovery-code records.",
    "oauth_authorizations": "OAuth authorization records issued to clients for users.",
    "oauth_client_states": "OAuth client state records for third-party provider flows.",
    "oauth_clients": "Registered OAuth client applications.",
    "oauth_consents": "User consent records for OAuth clients.",
    "one_time_tokens": "One-time token records associated with authentication users.",
    "refresh_tokens": "JWT refresh-token records, as described by the catalog comment.",
    "saml_providers": "SAML identity-provider connections, as described by the catalog comment.",
    "saml_relay_states": "SAML relay-state records for service-provider initiated logins.",
    "schema_migrations": "Authentication-system schema migration history.",
    "scim_tokens": "SCIM provisioning token records.",
    "scim_users": "Mappings between SCIM identities and authentication users.",
    "sessions": "Authentication session records associated with users.",
    "sso_domains": "Mappings from email domains to SSO providers.",
    "sso_providers": "Single-sign-on provider configuration records.",
    "users": "Secure authentication user-login records.",
    "webauthn_challenges": "WebAuthn registration or authentication challenge records.",
    "webauthn_credentials": "Registered WebAuthn credential records.",
}


def pii_kind(name: str, blocked: bool) -> str | None:
    lower = name.lower()
    if blocked or any(word in lower for word in ("token", "secret", "password", "hash", "key")):
        return "secret"
    if "email" in lower:
        return "email"
    if "phone" in lower:
        return "phone"
    if lower in {"ip", "ip_address"}:
        return "ip"
    if "name" in lower:
        return "name"
    return "pii"


def column_meaning(name: str) -> str:
    if name == "id":
        return "Identifier for this authentication-system record."
    if name.endswith("_id"):
        return f"Identifier reference named {name}; use the declared join graph where available."
    if name.endswith("_at"):
        return f"Timestamp associated with {name.removesuffix('_at').replace('_', ' ')}."
    if name in {"created", "updated"}:
        return f"Timestamp or state field named {name}."
    return f"Authentication-system field named {name}; its exact business semantics were not profiled."


def main() -> None:
    tables = json.loads((CATALOG / "tables.json").read_text(encoding="utf-8"))["rows"]
    columns = json.loads((CATALOG / "columns.json").read_text(encoding="utf-8"))["rows"]
    constraints = json.loads((CATALOG / "constraints.json").read_text(encoding="utf-8"))["rows"]
    joins = yaml.safe_load((KNOWLEDGE / "joins.yaml").read_text(encoding="utf-8")) or []
    policies = yaml.safe_load((KNOWLEDGE / "policies.yaml").read_text(encoding="utf-8")) or {}
    blocked = set(policies.get("blocked_columns") or [])
    pii = set(policies.get("pii_columns") or [])
    mandatory = policies.get("mandatory_filters") or {}

    by_table: dict[str, list[dict]] = {}
    for column in columns:
        if column["schema_name"] == "auth":
            by_table.setdefault(column["table_name"], []).append(column)
    primary: dict[str, list[str]] = {}
    foreign_columns: set[tuple[str, str]] = set()
    for constraint in constraints:
        if constraint["schema_name"] != "auth":
            continue
        fields = (constraint.get("columns") or "").split(",")
        if constraint["type"] == "p":
            primary[constraint["table_name"]] = fields
        if constraint["type"] == "f":
            foreign_columns.update((constraint["table_name"], field) for field in fields)

    target = KNOWLEDGE / "tables"
    target.mkdir(parents=True, exist_ok=True)
    for table in sorted((row for row in tables if row["schema_name"] == "auth"), key=lambda row: row["table_name"]):
        name = table["table_name"]
        table_fqn = f"auth.{name}"
        table_columns: dict[str, dict] = {}
        for column in sorted(by_table.get(name, []), key=lambda row: row["position"]):
            column_name = column["column_name"]
            fqn = f"{table_fqn}.{column_name}"
            card = {
                "type": column["data_type"],
                "meaning": column_meaning(column_name),
                "source": "fk" if (name, column_name) in foreign_columns else "llm_guess",
                "confidence": 1.0 if (name, column_name) in foreign_columns else 0.3,
            }
            if column.get("enum_values"):
                card["values"] = [value.strip() for value in column["enum_values"].split("|")]
            if fqn in pii:
                card["pii"] = pii_kind(column_name, fqn in blocked)
            table_columns[column_name] = card
        human_joins = []
        for edge in joins:
            if edge["left"] == table_fqn or edge["right"] == table_fqn:
                human_joins.append(
                    f"{edge['left']}.{','.join(edge['left_columns'])} = {edge['right']}.{','.join(edge['right_columns'])} "
                    f"({edge['cardinality']}, {edge['source']})"
                )
        summary = SUMMARIES[name]
        if table.get("comment"):
            summary = f"{table['comment']} Catalog access only; data profiling was not permitted."
        card = {
            "table": table_fqn,
            "domain": "auth",
            "status": "unknown",
            "summary": summary,
            "grain": f"One row per {name.replace('_', ' ')} record.",
            "synonyms": [name.replace("_", " ")],
            "stats": {"catalog_row_estimate": table.get("row_estimate"), "profile_error": "read access unavailable"},
            "key_columns": primary.get(name, []),
            "joins": human_joins,
            "gotchas": [
                "Managed authentication schema: the audit role could not read table data, so semantics are catalog-only.",
                "Contains authentication data and may include PII or credentials; do not use it for business reporting.",
            ],
            "mandatory_filters": mandatory.get(table_fqn, []),
            "sensitivity": "sensitive",
            "source": "llm_guess",
            "confidence": 0.3,
            "columns": table_columns,
        }
        (target / f"auth.{name}.yaml").write_text(yaml.safe_dump(card, sort_keys=False, allow_unicode=True), encoding="utf-8")


if __name__ == "__main__":
    main()
