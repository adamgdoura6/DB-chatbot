---
name: data-profiler
description: Step 2 of the database audit. Profiles each table with sampled SQL (row counts, null %, distinct counts, min/max, top values, freshness, JSONB keys), flags PII columns, and builds the value index. Use after catalog-crawler, or for scheduled stats refreshes.
---

# Data profiler + PII scanner

Cheap, sampled SQL only. Never run unbounded scans on large tables.
`../shared/dbq.py` masks PII in all output automatically; never try to get around that.

## Inputs
`../knowledge/_raw/catalog/tables.json`, `columns.json`. For an incremental audit, use the list of new or changed
tables from the db-onboarding skill.

## Per table

Pick a sample source:
- Small tables (`row_estimate` <= 200,000): `FROM <schema>.<table>` directly.
- Large tables: `FROM <schema>.<table> TABLESAMPLE SYSTEM (<pct>)`, where pct ≈ 100 * 30000 / row_estimate
  (minimum 0.01). Views cannot be sampled: use `LIMIT 30000` in a subquery.

Run these with `python ../shared/dbq.py --json` (templates in `queries.md` in this folder):

1. **Row count.** Exact `count(*)` for small tables; use `row_estimate` for large ones.
2. **Column stats.** One query per table that computes, for each column: null fraction, distinct count,
   min/max (numeric and date/time columns only). Skip `bytea`, `tsvector`, `geometry` and `vector` columns.
3. **Top values.** For every column with distinct count <= 200 (and every enum or status-like column): the top
   values with counts. If distinct count <= 200 AND the column is text-like AND not PII, the full list goes
   into the value index.
4. **Freshness.** `max()` of the most meaningful timestamp, in this order of preference: `updated_at`,
   `modified_at`, `created_at`, `inserted_at`, then any other timestamp column.
5. **JSONB keys.** For json/jsonb columns: the distinct top-level keys in the sample.
6. **Samples.** 5 sample rows (`LIMIT 5`). They come back masked.

## PII detection
Mark a column as PII (kind: email, phone, name, address, iban, card, birthdate, national_id, ip, secret, health)
when either is true:
- its name suggests it (`email`, `phone`, `first_name`, `iban`, `password_hash`, `dob`, ...), or
- dbq returned masked tokens for it (`user_xxxxxx@domain`, `<phone:...>`, `<iban:...>`): dbq detected the
  values by pattern.

For each PII column:
- add it to `pii_columns` in `../knowledge/policies.yaml`;
- if it is a secret (passwords, tokens, API keys, hashes), also add it to `blocked_columns`;
- never put its values in `values.yaml` or in any card.

## Output
- `../knowledge/_raw/profiles/<schema>.<table>.json`:
  ```json
  {"table": "public.orders", "rows": 1200000, "sampled": true,
   "freshness": {"column": "created_at", "max": "2026-10-08T09:12:00Z"},
   "columns": {"status": {"null_pct": 0, "distinct": 3, "top": [["2", 900000], ["1", 200000], ["3", 100000]]},
               "email": {"pii": "email"}},
   "samples": [ ... masked rows ... ]}
  ```
- Value index entries added to `../knowledge/values.yaml` (format in the knowledge-store skill).
- Updated `../knowledge/policies.yaml` (`pii_columns`, `blocked_columns`).

## Budget
Use a timeout of 20000 ms. If a query on a table times out, record `"profile_error": "timeout"` and move on.
Do not retry with a bigger scan. Work table by table, and keep going when one table fails.
