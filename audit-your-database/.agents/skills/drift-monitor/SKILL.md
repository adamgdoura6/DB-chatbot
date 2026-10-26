---
name: drift-monitor
description: Keeps the knowledge fresh as the database changes - detects schema changes via structure hashes, triggers an incremental re-audit of only the affected tables, re-runs verified queries that touch changed tables (flagging broken ones), refreshes stats and the value index, and re-verifies old facts. Run on a schedule (nightly) or when the user says the schema changed.
---

# Drift monitor

## 1. Schema changes (nightly)
1. Run `.agents/skills/catalog-crawler/queries/hashes.sql` with `../shared/dbq.py --json --max-rows 20000`.
2. Compare it with `../knowledge/_raw/catalog/hashes.json`. The differences fall into:
   - **added** tables: audit them, and put them into a domain;
   - **removed** tables: delete their cards, edges, values and glossary references; mark verified queries that
     use them as `broken: true`;
   - **changed** tables: re-audit them.
3. If anything changed, run db-onboarding in **incremental** mode, limited to those tables.
4. **Re-run every verified query that touches an added, changed or removed table.** If it fails or the result
   shape changed (columns or row count): `broken: true`. Broken queries are never used as examples, and
   human-review lists them.

## 2. Stats and value index (daily or weekly)
- Re-run data-profiler steps 1, 3 and 4 for all tables: row counts, top values, freshness. Update `stats:` in the
  cards and the `values:` lists in `values.yaml`. Keep the `aliases`.
- New values (new cities, products, plan tiers) show up here. Without this, the bot can't map user words to
  WHERE clauses.
- A table whose freshness stopped moving while it used to grow daily: add a `stale` flag to `quality.yaml` and
  mention it in the gaps report.

## 3. Re-verify old facts (weekly)
- Verified queries with `last_verified` older than 30 days: re-run them, and update `last_verified` or set
  `broken`.
- Column facts with `source: verified` that are older than 90 days: re-run their checks (knowledge-verifier,
  step 1).

## 4. Mine query logs (weekly)
Re-run `query-log.sql`. Join patterns or filters not yet in `joins.yaml` or the glossary become proposals in
`../learning/proposals/`, with `root_cause: not_retrieved`. They go through knowledge-promotion like any other
learning.

## Commit
`git commit -am "knowledge: drift check <date> (+A ~C -R tables, N queries re-verified, B broken)"`.
