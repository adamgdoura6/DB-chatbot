# Supabase

Supabase is PostgreSQL, so it is fully supported.

## 1. Create a read-only role
Do **not** use the `postgres` password or the `service_role` key. Both can write, and `service_role` bypasses
Row Level Security.

1. Open **SQL Editor** in the Supabase dashboard.
2. Paste [`readonly-role.sql`](readonly-role.sql), change the password, and run it.
3. **Row Level Security.** Tables with RLS enabled return **zero rows** to `ai_reader` unless a policy lets it
   read them. To let it read every row of the RLS tables in `public`, run:

   ```sql
   DO $$
   DECLARE t record;
   BEGIN
     FOR t IN SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'public' AND rowsecurity LOOP
       EXECUTE format('CREATE POLICY ai_reader_select ON %I.%I FOR SELECT TO ai_reader USING (true)',
                      t.schemaname, t.tablename);
     END LOOP;
   END $$;
   ```
   Run it again after you add new RLS tables. If you'd rather the bot see only some rows, write narrower
   `USING (...)` conditions instead. The `auth` and `storage` schemas are managed by Supabase; leave them out
   unless you need them.

## 2. Get the connection string
Dashboard → **Connect** → **Session pooler** (works over IPv4; the direct connection is IPv6-only unless you
have the IPv4 add-on). It looks like:

```
postgresql://ai_reader.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

Note the user is `ai_reader.<project-ref>` (the pooler needs the project ref), not `postgres.<project-ref>`.

## 3. Connect
```bash
cd audit-your-database
python connect.py          # choose "Supabase", paste the URL; the password is asked separately if missing
```

## Troubleshooting
| error | fix |
|---|---|
| `password authentication failed` | user must be `ai_reader.<project-ref>` on the pooler |
| `Tenant or user not found` | wrong region in the pooler host, or a typo in the project ref |
| connects, but every table shows 0 rows | RLS: run step 1.3 |
| `could not translate host name` on `db.<ref>.supabase.co` | IPv6-only direct host; use the session pooler |
