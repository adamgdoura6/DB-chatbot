# Profiling query templates

Replace `<t>` with the schema-qualified table, `<src>` with the sample source, and repeat the per-column
expressions for each column. Quote unusual identifiers with double quotes.

## Sample source
```sql
-- small table
<src> = public.orders
-- large table (row_estimate 5,000,000 -> 30,000 / 5,000,000 * 100 = 0.6)
<src> = public.orders TABLESAMPLE SYSTEM (0.6)
-- view
<src> = (SELECT * FROM public.v_sales LIMIT 30000) s
```

## Row count (small tables only)
```sql
SELECT count(*) AS n FROM public.orders
```

## Column stats (one query per table)
```sql
SELECT count(*) AS n,
       -- for every column c:
       round(1 - count(c)::numeric / nullif(count(*), 0), 4) AS c__null_frac,
       count(DISTINCT c) AS c__distinct,
       -- only numeric / date / timestamp columns:
       min(c)::text AS c__min, max(c)::text AS c__max
FROM <src>
```
Do not take `count(DISTINCT ...)` on json columns. Use `count(DISTINCT c::text)` for jsonb if needed.

## Top values (columns with distinct <= 200)
```sql
SELECT c::text AS value, count(*) AS n
FROM <src>
WHERE c IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC
LIMIT 200
```

## Freshness (full table, uses an index if one exists)
```sql
SELECT max(updated_at) AS freshest FROM public.orders
```

## JSONB keys
```sql
SELECT DISTINCT jsonb_object_keys(c::jsonb) AS key
FROM <src>
WHERE jsonb_typeof(c::jsonb) = 'object'
LIMIT 100
```

## Samples
```sql
SELECT * FROM <src> LIMIT 5
```

## Growth rate (optional, tables with created_at)
```sql
SELECT date_trunc('month', created_at) AS month, count(*) AS n
FROM <src>
WHERE created_at > now() - interval '6 months'
GROUP BY 1 ORDER BY 1
```
