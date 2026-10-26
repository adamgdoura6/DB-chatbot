-- One row per column, with type, nullability, default, comment and enum labels.
SELECT n.nspname AS schema_name, c.relname AS table_name, a.attnum AS position, a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS data_type,
       NOT a.attnotnull AS nullable,
       pg_get_expr(d.adbin, d.adrelid) AS default_value,
       col_description(c.oid, a.attnum) AS comment,
       CASE WHEN t.typtype = 'e' THEN
            (SELECT string_agg(e.enumlabel, ' | ' ORDER BY e.enumsortorder) FROM pg_enum e WHERE e.enumtypid = t.oid)
       END AS enum_values
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_type t ON t.oid = a.atttypid
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE a.attnum > 0 AND NOT a.attisdropped
  AND c.relkind IN ('r', 'p', 'v', 'm', 'f') AND NOT c.relispartition
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg\_%'
ORDER BY 1, 2, 3
