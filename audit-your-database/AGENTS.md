# Audit your database: agent instructions

This folder connects to the customer database and audits it. The result, the audit report, is the knowledge
store in `../knowledge/`. `../talk-to-your-database/` reads it to answer questions.

The rules in `../AGENTS.md` apply here; read them first. Run every command from this folder.

## Paths
- database: `python ../shared/dbq.py "<sql>"` (the only access path)
- audit report: `../knowledge/` (format: `../shared/skills/knowledge-store/SKILL.md`)
- skills: `.agents/skills/<name>/SKILL.md`. If your agent does not load skills automatically, open the right
  `SKILL.md` and follow it.

## What the user wants → what to do

| user intent | do this |
|---|---|
| connect a database / change the connection | ask the user to run `python connect.py` **in their own terminal** (it asks for the password). Afterwards, run `python connect.py --check` |
| "is it connected?" | `python connect.py --check` |
| which databases are supported | `python connect.py --list`, details in `providers/README.md` |
| audit / onboard / "learn my database" / re-audit after schema changes | `.agents/skills/db-onboarding/SKILL.md` |
| schema changed / refresh stats | `.agents/skills/drift-monitor/SKILL.md` |
| answer the audit's open questions | `../shared/skills/human-review/SKILL.md` |
| a question about the data ("how many…") | that's the other folder: `../talk-to-your-database/` (tell the user, and follow its `AGENTS.md` if they want you to answer now) |

Building blocks called by db-onboarding, in order: `catalog-crawler`, `data-profiler`, `relationship-analyst`,
`domain-clusterer`, `table-interpreter`, `quality-auditor`, `knowledge-synthesizer`, `knowledge-verifier`, then
`human-review` (in `../shared/skills/`).

## Supported databases
PostgreSQL and everything built on it: Supabase, AWS RDS / Aurora PostgreSQL, Neon, Cloud SQL, Azure, ...
Firebase, MySQL, DynamoDB, Snowflake and BigQuery are planned (`providers/`). If the user has one of those, say
so plainly; don't try to audit it another way.

## Subagents
Where the architecture calls for parallel work (the table-interpreter runs once per domain, the
knowledge-verifier per domain), use your agent's subagent or task feature if it has one. Give each subagent its
skill path and the exact files to read and write. Without subagents, do the same work sequentially.
