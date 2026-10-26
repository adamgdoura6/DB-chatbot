# Database providers

| provider | status | guide |
|---|---|---|
| Supabase | supported | [supabase.md](supabase.md) |
| AWS RDS / Aurora (PostgreSQL) | supported | [aws.md](aws.md) |
| Any other PostgreSQL (self-hosted, Neon, Cloud SQL, Azure, Firebase Data Connect, ...) | supported | [postgres.md](postgres.md) |
| Firebase / Firestore | planned | [firebase.md](firebase.md) |
| AWS RDS / Aurora (MySQL), MySQL, MariaDB, PlanetScale | planned | |
| AWS DynamoDB | planned | |
| Snowflake | planned | |
| Google BigQuery | planned | |

`python connect.py --list` prints the same list.

Every supported provider uses the same read-only role: [`readonly-role.sql`](readonly-role.sql).

## Adding an engine
An engine needs three things, in this order:
1. **A guarded runner.** `shared/dbq.py` is Postgres-only (sqlglot `postgres` dialect, `BEGIN READ ONLY`,
   `EXPLAIN (FORMAT JSON)`). A new engine needs the same guarantees: read-only, one statement, row cap, timeout,
   blocked columns, injected filters, PII masking.
2. **Catalog queries** for the engine, in the same output shape as
   `.agents/skills/catalog-crawler/queries/*.sql`, so the later audit steps don't change.
3. **An entry in `PROVIDERS`** in `connect.py`, with its engine added to `SUPPORTED_ENGINES`.
