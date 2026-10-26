-- Indexes (needed to know which filters are cheap) and partition keys.
SELECT n.nspname AS schema_name, c.relname AS table_name, i.relname AS index_name,
       ix.indisunique AS is_unique, ix.indisprimary AS is_primary,
       pg_get_indexdef(ix.indexrelid) AS definition
FROM pg_index ix
JOIN pg_class c ON c.oid = ix.indrelid
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg\_%'
UNION ALL
SELECT n.nspname, c.relname, '(partition key)', false, false, pg_get_partkeydef(c.oid)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'p' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2, 3
