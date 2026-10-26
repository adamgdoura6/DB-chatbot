# Any other PostgreSQL

Self-hosted Postgres, Neon, Google Cloud SQL, Azure Database for PostgreSQL, Crunchy, Aiven,
Firebase Data Connect (it is Cloud SQL for PostgreSQL), and anything else that speaks the Postgres protocol.

1. As an admin, run [`readonly-role.sql`](readonly-role.sql) (change the password, repeat the schema block per
   schema).
2. Make sure your machine can reach the database (firewall / authorized networks / tunnel).
3. Connect:
   ```bash
   cd audit-your-database
   python connect.py          # choose "Any other PostgreSQL"
   ```
   The default is `sslmode=prefer`. Add `?sslmode=require` to the URL if your host requires SSL (Neon, Azure
   and most hosted providers do).

Postgres-compatible engines that are not real Postgres (CockroachDB, Redshift, YugabyteDB) may fail in the
catalog crawl; issues and fixes are welcome.
