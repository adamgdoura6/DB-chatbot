-- Most-used queries that join tables (requires the pg_stat_statements extension; skip if it errors).
SELECT calls, left(regexp_replace(query, '\s+', ' ', 'g'), 2000) AS query
FROM pg_stat_statements
WHERE query ILIKE '%join%' AND query NOT ILIKE '%pg_catalog%'
ORDER BY calls DESC
LIMIT 300
