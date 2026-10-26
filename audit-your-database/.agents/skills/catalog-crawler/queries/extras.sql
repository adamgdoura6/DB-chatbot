-- Extensions, RLS policies, triggers and functions in one pass (kind column tells them apart).
SELECT 'extension' AS kind, extname AS name, NULL AS table_name, extversion AS detail FROM pg_extension
UNION ALL
SELECT 'rls_policy', policyname, schemaname || '.' || tablename,
       cmd || ' to ' || array_to_string(roles, ',') || ' using ' || coalesce(qual, 'true') FROM pg_policies
UNION ALL
SELECT 'trigger', t.tgname, n.nspname || '.' || c.relname, pg_get_triggerdef(t.oid)
FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT t.tgisinternal AND n.nspname NOT IN ('pg_catalog', 'information_schema')
UNION ALL
SELECT 'function', p.proname, n.nspname, pg_get_function_identity_arguments(p.oid)
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg\_%'
ORDER BY 1, 3, 2
