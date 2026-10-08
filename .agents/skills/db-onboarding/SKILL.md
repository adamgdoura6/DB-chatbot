---
name: db-onboarding
description: Entry point for auditing a customer database. Runs the full onboarding audit in order (catalog-crawler, data-profiler, relationship-analyst, domain-clusterer, table-interpreter per domain in parallel, quality-auditor, knowledge-synthesizer, knowledge-verifier, human-review) and commits the resulting knowledge store. Use when a database is connected for the first time, or to re-audit after schema changes.
---

# Database onboarding audit

You orchestrate. Each step is its own skill in `.agents/skills/<name>/SKILL.md`: read it and follow it. Steps
have clear inputs and outputs on disk (see the knowledge-store skill), so the audit can be resumed: if a step's
output already exists for this run, skip it.

## Before starting
1. Check the connection: `python tools/dbq.py "SELECT current_database(), current_user, version()"`.
   If that fails, stop and ask the user to set `DBCHAT_DATABASE_URL`.
2. Check that the connection really is read-only:
   `python tools/dbq.py "SELECT has_database_privilege(current_user, current_database(), 'CREATE') AS can_create"`.
   If the role can write, warn the user and recommend a dedicated read-only role. Continue only if they agree.
3. Ask the user for the scope (schemas to include) if not given. Default: all non-system schemas.
4. Full audit or incremental: if `knowledge/_raw/catalog/hashes.json` exists, re-run only the `hashes.sql`
   query from catalog-crawler and compare. Tables with a new or changed hash are the **work set**. Unchanged
   tables keep their cards. If nothing changed, say so and stop.

## Pipeline

| # | skill | input | output | notes |
|---|---|---|---|---|
| 1 | catalog-crawler | database | `_raw/catalog/*.json` | always the full catalog |
| 2 | data-profiler | catalog | `_raw/profiles/`, `values.yaml`, `policies.yaml` (PII) | work set only |
| 3 | relationship-analyst | catalog, profiles, query log | `joins.yaml` | whole graph (cheap), re-verify edges touching the work set |
| 4 | domain-clusterer | joins | `domains/*.md` (table lists) | keep existing domain names when possible |
| 5 | table-interpreter | one domain each | `tables/*.yaml`, open questions | **parallel subagents, one per domain**; only domains containing work-set tables |
| 6 | quality-auditor | catalog, profiles, joins, cards | `quality.yaml`, card status | may run in parallel with 5 |
| 7 | knowledge-synthesizer | cards | `overview.md`, `domains/*.md`, `glossary.yaml` | |
| 8 | knowledge-verifier | everything | verified claims, metrics, `verified-queries.yaml` | can be parallel per domain |
| 9 | human-review | open questions | questions shown to the user | the audit is usable before they are answered |

Parallelism: if your agent can spawn subagents (Claude Code Task/Agent tool, Codex subagents, Copilot agent
mode), give each subagent one domain, the path to its skill file, and the paths to read and write. Subagents
write their own files and return a short summary. If your agent cannot spawn subagents, process the domains one
after another.

## Finish
1. Make sure every table in the catalog has a card. If a table has none, write a minimal card from the catalog
   with `confidence: 0.2`.
2. Check that `policies.yaml` is valid YAML: `python tools/dbq.py --check "SELECT 1"` must succeed.
3. Commit: `git add knowledge && git commit -m "knowledge: audit <N> tables (<full|incremental>)"`.
   If this is not a git repository, run `git init` first (ask the user once).
4. Report to the user: number of tables, domains, joins (declared/inferred), glossary terms, verified queries,
   open questions, and the 3-5 most important gotchas found. Then show the open questions (human-review).
