---
name: relationship-analyst
description: Step 3 of the database audit. Builds the join graph from declared foreign keys plus undeclared relationships (naming conventions, query logs, polymorphic type/id pairs), verifies every inferred join with a value-overlap SQL check, and records cardinality and confidence in knowledge/joins.yaml.
---

# Relationship analyst

Real databases are full of joins nobody declared (`user_id` with no FK). Find them, but **never trust a join you
have not verified on data.**

## 1. Declared foreign keys
From `knowledge/_raw/catalog/constraints.json`, rows with `type = 'f'`. Each becomes an edge with
`source: fk, confidence: 1.0`.

## 2. Candidate undeclared joins
Collect candidates from four places. Skip any candidate that is already a declared FK.

1. **Query logs** (`_raw/catalog/query-log.json`). Join conditions `a.x = b.y` in real queries are the best
   evidence there is: they show how the business actually joins tables.
2. **Naming.** `<thing>_id`, `<thing>_uuid`, `<thing>Id` → a table named `<thing>`, `<thing>s`, `<thing>es` or
   `<thin>ies`. The target column is that table's single-column primary key. Also: a column with the same name
   as another table's non-`id` primary key (e.g. `customer_number`). The column types must be compatible
   (integer family, uuid, or text family).
3. **Polymorphic pairs.** `<x>_type` + `<x>_id` in the same table. Use the top values of `<x>_type` (from the
   profile) to map each type value to a table (`'Order'` → orders). This gives one edge per value, with
   `condition_extra: "<x>_type = 'Order'"`.
4. **Your judgement.** Leftover reference-like columns (`created_by`, `owner`, `parent_id`, `assignee`,
   `author`). Propose the most plausible target (e.g. `created_by` → `users.id`; `parent_id` → same table).

## 3. Verify every candidate (value overlap / inclusion check)

```sql
WITH l AS (
  SELECT DISTINCT <left_col> AS v FROM <left_table> WHERE <left_col> IS NOT NULL [AND <type_col> = '<value>']
  LIMIT 5000
)
SELECT count(*) AS total,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM <right_table> r WHERE r.<right_col> = l.v)) AS hit
FROM l
```
If the column types differ, cast both sides with `::text`. Use `--timeout-ms 20000`.

- overlap = hit / total
- Accept only if overlap >= 0.9. Then set confidence = overlap × base, where the base is 0.95 for a query log,
  0.9 for naming or polymorphic, and 0.8 for judgement.
- Rejected candidates go to `knowledge/_raw/relationships.json` with their overlap, for the record.
- 0.9 <= overlap < 1.0 means orphan rows exist. Tell the quality-auditor (record the percentage).

## 4. Cardinality (left:right)
The right side is unique if it is a primary key or has a unique constraint or unique index. Do the same check on
the left side.

| left unique? | right unique? | cardinality |
|---|---|---|
| yes | yes | 1:1 |
| no | yes | N:1 |
| yes | no | 1:N |
| no | no | N:M (suspicious: re-check) |

**Junction tables**: two outgoing edges to different tables and almost no other columns besides timestamps.
They mean an N:M between the two targets. Note them in both table cards.

## Output
`knowledge/joins.yaml`, sorted by `left`, in the format from the knowledge-store skill. Report the result in one
line, e.g. `64 declared, 23 inferred (verified), 7 rejected, 3 junction tables`.
