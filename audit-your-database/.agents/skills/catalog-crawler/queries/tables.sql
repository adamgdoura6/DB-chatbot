-- One row per table / view / materialized view in user schemas.
SELECT n.nspname AS schema_name, c.relname AS table_name,
       CASE c.relkind WHEN 'r' THEN 'table' WHEN 'p' THEN 'partitioned_table'
                      WHEN 'v' THEN 'view' WHEN 'm' THEN 'materialized_view' WHEN 'f' THEN 'foreign_table' END AS kind,
       obj_description(c.oid, 'pg_class') AS comment,
       GREATEST(c.reltuples, 0)::bigint AS row_estimate,
       pg_total_relation_size(c.oid) AS bytes,
       c.relrowsecurity AS rls_enabled,
       CASE WHEN c.relkind IN ('v', 'm') THEN pg_get_viewdef(c.oid, true) END AS view_definition
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
  AND NOT c.relispartition
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg\_%'
ORDER BY 1, 2
