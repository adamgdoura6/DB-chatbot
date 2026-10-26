---
name: catalog-crawler
description: Step 1 of the database audit. Reads the Postgres system catalog (tables, columns, types, keys, foreign keys, indexes, enums, views, RLS policies, triggers, extensions, structure hashes) into ../knowledge/<db>/_raw/catalog/. Use at onboarding or when the schema may have changed.
---

# Catalog crawler

Deterministic step: no interpretation. Run the prepared SQL files and save their output exactly.
Do not write your own catalog queries unless a file fails.

## Steps

From the repository root, run each query and save its JSON output:

```bash
mkdir -p ../knowledge/<db>/_raw/catalog
for q in tables columns constraints indexes extras hashes; do
  python ../shared/dbq.py --json --max-rows 20000 --timeout-ms 60000 \
    --file .agents/skills/catalog-crawler/queries/$q.sql > ../knowledge/<db>/_raw/catalog/$q.json
done
python ../shared/dbq.py --json --max-rows 300 --file .agents/skills/catalog-crawler/queries/query-log.sql \
  > ../knowledge/<db>/_raw/catalog/query-log.json || echo '{"rows": [], "note": "pg_stat_statements unavailable"}' > ../knowledge/<db>/_raw/catalog/query-log.json
```

On Windows PowerShell, run the same `python ../shared/dbq.py ...` commands one by one, with `> file` redirects.

## Checks before you move on
- `tables.json` has `"truncated": false`. If it is truncated, the database is very large: crawl schema by schema
  by adding `AND n.nspname = '<schema>'` to the queries.
- If the user limited the audit to certain schemas, drop other schemas' rows from every file now, and note the
  scope in `../knowledge/<db>/overview.md`.
- Count the tables, views and foreign keys and report them in one line, e.g. `Crawled 87 tables, 12 views, 64 FKs`.

## What the files contain
| file | one row per |
|---|---|
| tables.json | table/view/matview (kind, comment, row_estimate, bytes, rls_enabled, view_definition) |
| columns.json | column (type, nullable, default, comment, enum_values joined by ` \| `) |
| constraints.json | constraint: type p=primary key, f=foreign key (ref_table, ref_columns), u=unique, c=check |
| indexes.json | index definition, plus partition keys |
| extras.json | extension, rls_policy, trigger, function |
| hashes.json | table_fqn -> structure_hash (incremental audits, drift-monitor) |
| query-log.json | most-called queries containing joins (relationship-analyst) |

Large tables are those with `row_estimate` > 200,000 or `bytes` > 1 GB. The data-profiler samples them
instead of scanning them.
