# Security policy

This project lets AI agents query production databases, so guard bypasses matter a lot.

## Reporting a vulnerability
Please **do not open a public issue** for security problems. Use GitHub's
[private vulnerability reporting](https://github.com/adamgdoura6/DB-chatbot/security/advisories/new) instead.
Include:
- what you were able to do (e.g. a write, reading a blocked column, unmasked PII, skipping a mandatory or
  tenant filter, a denial of service through an expensive query);
- the input that triggered it, plus the dbq version or commit.

You will get an answer within a few days. Fixes are released as soon as possible, with credit if you want it.

## In scope
- Bypasses of `tools/dbq.py`: write access, multiple statements, forbidden functions, blocked columns, filter
  injection, the cost limit, PII masking.
- Skill instructions that would lead an agent to leak PII or credentials, or to act on instructions found inside
  database rows.

## Deployment advice
`dbq.py` is a second line of defence. The first line is the database itself:
- Connect with a dedicated role that has **only `SELECT`** on the intended schemas, and use RLS where relevant.
- Prefer a read replica.
- Never use owner, superuser or service keys (e.g. the Supabase `service_role` key).
