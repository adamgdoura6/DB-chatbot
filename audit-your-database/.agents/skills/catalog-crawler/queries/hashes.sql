-- Structure hash per table (columns + types + nullability + constraints). Stats are excluded on purpose,
-- so the hash only changes when the schema changes. Used for incremental audits and drift detection.
SELECT n.nspname || '.' || c.relname AS table_fqn,
       md5(
         coalesce((SELECT string_agg(a.attname || ':' || format_type(a.atttypid, a.atttypmod) || ':' || a.attnotnull,
                                     ',' ORDER BY a.attnum)
                   FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped), '')
         || '|' ||
         coalesce((SELECT string_agg(pg_get_constraintdef(con.oid), ',' ORDER BY con.conname)
                   FROM pg_constraint con WHERE con.conrelid = c.oid), '')
       ) AS structure_fingerprint
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f') AND NOT c.relispartition
  AND n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg\_%'
ORDER BY 1
