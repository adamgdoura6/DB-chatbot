---
name: quality-auditor
description: Step 6 of the database audit (can run alongside table-interpreter). Finds legacy and temp tables, empty and stale tables, orphan rows, duplicates, missing primary keys, soft-delete and test-data markers, and overlapping sources of truth; writes ../knowledge/quality.yaml and decides canonical vs legacy.
---

# Quality auditor

Most checks are mechanical. Use judgement only to decide between canonical and legacy.

## Checks
| kind | how to detect | severity |
|---|---|---|
| legacy_name | name matches `_old`, `_bak`, `_backup`, `_copy`, `_tmp`, `_v2`, `_2023`, `tmp_*`, `old_*`, `test_*` | warn |
| empty | 0 rows | info |
| stale | freshness more than 180 days behind the freshest table in the database | warn |
| no_primary_key | base table without a primary key (duplicates possible) | warn |
| duplicate_rows | no PK, or a natural key that should be unique: `SELECT k, count(*) FROM t GROUP BY k HAVING count(*) > 1 LIMIT 5` | warn |
| orphans | join overlap < 1.0 (from relationship-analyst): "3.2% of orders.customer_id have no customer" | warn if > 2% |
| soft_delete | columns `deleted_at`, `is_deleted`, `archived_at`, `removed_at` | info → mandatory filter |
| test_data | columns `is_test`, `is_demo`, `is_internal`, `livemode`; test email domains (example.com, test.com) in masked emails | info → gotcha |
| duplicate_table | two tables whose column sets overlap ≥ 80% | warn → decide canonical |
| inconsistent_format | mixed formats in one column, e.g. country as `DE` / `Germany` / `de` in top values | info → gotcha |

## Canonical vs legacy (judgement)
For each `duplicate_table` pair or `legacy_name` table, compare freshness, row growth, which one other tables
join to, and which one appears in the query logs. Then decide which table is canonical, and record the reason.
If the evidence conflicts, add an open question.

## Output
`../knowledge/quality.yaml`:
```yaml
- table: public.orders_old
  kind: duplicate_table
  detail: 92% column overlap with public.orders; last row 2024-03-01; no query-log usage
  severity: warn
  decision: legacy (orders is canonical)
```
Then pass the decisions on:
- set `status: legacy` in the table cards;
- turn soft-delete and test-data findings into gotchas or `mandatory_filters` in the table cards and in
  `policies.yaml`.
