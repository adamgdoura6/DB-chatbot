-- Dedicated read-only login for the audit and the chatbot. Works on any PostgreSQL: Supabase (SQL editor),
-- AWS RDS / Aurora (psql as the master user), self-hosted, Neon, Cloud SQL, Azure.
-- Run it yourself as an admin. The agents never run this: they only ever get the read-only login.
--
-- 1. Change the password.
-- 2. Repeat the "per schema" block for every schema the bot may see (default: public only).

CREATE ROLE ai_reader WITH LOGIN PASSWORD 'change-me-to-a-long-random-password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

-- Belt and braces: every session of this role is read-only, with a server-side timeout.
ALTER ROLE ai_reader SET default_transaction_read_only = on;
ALTER ROLE ai_reader SET statement_timeout = '60s';
ALTER ROLE ai_reader SET idle_in_transaction_session_timeout = '60s';

DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO ai_reader', current_database()); END $$;

-- ---- per schema --------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO ai_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ai_reader;          -- tables, views, materialized views
-- Tables created later by the role running this script are readable too
-- (add FOR ROLE <owner> if another role creates your tables):
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ai_reader;
-- ------------------------------------------------------------------------------

-- Optional, recommended: lets the relationship analyst learn real join patterns from pg_stat_statements.
-- (Skip it if your platform does not allow granting it.)
GRANT pg_read_all_stats TO ai_reader;
