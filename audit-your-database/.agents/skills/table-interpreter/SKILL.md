---
name: table-interpreter
description: Step 5 of the database audit. Interprets one business domain at a time and writes a table card per table, with column cards (meaning, grain, units, decoded enum values, which timestamp means what, soft deletes, gotchas, mandatory filters, synonyms) plus open questions for anything uncertain. Designed to run as one parallel subagent per domain.
---

# Table interpreter (one domain per run)

This is where the business meaning comes from. On real databases, text-to-SQL fails because of missing context
like this, not because of SQL syntax. Be precise, ground every claim in evidence, and admit uncertainty.

**Run it as one subagent per domain, in parallel, if your agent supports subagents.** Otherwise run it domain
by domain. Interpret a whole domain together: a table makes more sense next to its neighbours.

## Input for domain `<D>`
- The table list from `../knowledge/<db>/domains/<D>.md`.
- For each table, from `_raw/catalog/*.json`: columns, types, keys, comments, enums, check constraints, view
  definition.
- From `_raw/profiles/<table>.json`: stats, top values, freshness, masked samples.
- The edges touching these tables in `../knowledge/<db>/joins.yaml`, and the summaries of linked tables in other
  domains (if their cards exist).
- The flags for these tables in `../knowledge/<db>/quality.yaml` (if quality-auditor already ran).

You may run small extra queries with `../shared/dbq.py` to settle a question, e.g. to check
`SELECT status, count(*), min(amount), max(amount) FROM orders GROUP BY 1`. Keep them cheap (LIMIT,
aggregates, `--timeout-ms 15000`).

## What to decide, per table
- **summary**: what it represents in business terms. **grain**: what exactly one row is.
- **status**: `canonical`, `legacy` (superseded, abandoned, `_old`, stale), `test`, or `unknown`. When two
  tables overlap, decide which one is the source of truth, and say why.
- **columns**, each with:
  - meaning;
  - **unit** where relevant: `EUR cents` vs `EUR`, `UTC` vs local time, seconds vs milliseconds, percent
    0-1 vs 0-100;
  - **values**: decoded codes (`1: pending, 2: paid, 3: refunded`), based on top values, check constraints,
    enum labels, column comments and how the codes co-occur with other columns;
  - what each timestamp marks (`created_at` = row inserted, `paid_at` = payment captured);
  - synonyms that business users would say.
- **gotchas**: anything that makes a naive query wrong. Examples: soft deletes (`deleted_at`), test or
  internal rows, refunds included in totals, duplicate rows, mixed currencies, amounts in cents, a legacy twin
  table, time zones, or a fan-out when joining.
- **mandatory_filters**: SQL predicates (unqualified column names) that every business query must apply, e.g.
  `deleted_at IS NULL`. Only include filters you are confident about. They become enforced policy.
- **sensitivity**: `pii` if any column is PII.
- **source / confidence** per table and per column. Use `llm_guess` with your honest confidence. Use
  `verified` only for facts you just checked with a query.

## Uncertainty → open questions
When the evidence cannot settle something that matters, give your best guess with low confidence **and** add a
question to `../knowledge/<db>/open-questions.yaml`. Typical cases: cents or euros, what a code means, which of two
tables is current, whether test data is mixed in. Phrase each question so a data owner can answer it in
seconds, and include your current guess.

## Output
- One file per table, `../knowledge/<db>/tables/<schema>.<table>.yaml`, in exactly the format from the knowledge-store
  skill.
- Mandatory filters appended to `../knowledge/<db>/policies.yaml` under `mandatory_filters`.
- New entries in `../knowledge/<db>/open-questions.yaml`. Ids: `oq-<domain>-<n>`, so parallel runs never collide.

When running as a subagent, return a short summary only: tables written, number of open questions, and the
biggest gotchas. The files are the real output.
