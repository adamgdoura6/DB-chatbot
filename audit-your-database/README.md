# Audit your database

Connect your database, then let an agent audit it: what every table holds, how tables connect, where each kind
of information lives, and which business rules apply. The audit report lands in [`../knowledge/`](../knowledge)
and is what [`../talk-to-your-database/`](../talk-to-your-database) uses to answer questions.

## 1. Connect

```bash
pip install -r requirements.txt     # from the repository root
cd audit-your-database
python connect.py
```

`connect.py` asks where your database lives, takes the connection (the password is never echoed), tests it
through `shared/dbq.py`, warns if the login can write, and saves it to the git-ignored `.env` at the repository
root.

| provider | status | guide |
|---|---|---|
| Supabase | supported | [providers/supabase.md](providers/supabase.md) |
| AWS RDS / Aurora (PostgreSQL) | supported | [providers/aws.md](providers/aws.md) |
| Any other PostgreSQL (self-hosted, Neon, Cloud SQL, Azure, ...) | supported | [providers/postgres.md](providers/postgres.md) |
| Firebase / Firestore | planned | [providers/firebase.md](providers/firebase.md) |
| MySQL / RDS MySQL, DynamoDB, Snowflake, BigQuery | planned | [providers/README.md](providers/README.md) |

Always connect with a dedicated **read-only** login: [providers/readonly-role.sql](providers/readonly-role.sql).

Check the connection at any time: `python connect.py --check`.

## 2. Audit

Open this folder in your agent and say **"Audit my database"**.

| agent | how |
|---|---|
| Claude Code | `claude --add-dir ..` in this folder |
| Codex | `codex --add-dir ..` in this folder |
| GitHub Copilot (VS Code), Cursor | open the **repository root** as the workspace, then: *"Audit my database"* |
| any other | point it to [`AGENTS.md`](AGENTS.md) |

`--add-dir ..` lets the agent write the report into `../knowledge/`, outside this folder.

The audit runs these skills (in [`.agents/skills/`](.agents/skills)):

```
catalog-crawler → data-profiler (+PII) → relationship-analyst → domain-clusterer
  → table-interpreter (one subagent per domain) ‖ quality-auditor
  → knowledge-synthesizer → knowledge-verifier → human-review
```

It ends with a summary (tables, domains, joins, glossary terms, verified queries, the top gotchas) and a short
list of questions only you can answer, e.g. *"Is `orders.amount` in cents or euros?"*. Answering them makes the
chatbot much more accurate, but the report is usable before you do.

## 3. Keep it fresh

When the schema changes, say *"the schema changed"* (drift-monitor). Only new or changed tables are re-audited.
The learning loop in `talk-to-your-database` also runs the drift check every night.

## What's in the report

```
../knowledge/
  overview.md            one page: the business, the domains, cross-cutting caveats
  domains/<domain>.md    tables per domain, key entities, common questions
  tables/<table>.yaml    table + column cards: meaning, units, value codes, gotchas, confidence
  joins.yaml             how tables connect (declared and inferred, with cardinality)
  glossary.yaml          business terms and metric definitions with SQL
  values.yaml            real filter values and aliases ("muc" → Munich)
  verified-queries.yaml  question → SQL pairs tested on your data
  quality.yaml           legacy / stale / duplicate tables, orphan rows
  open-questions.yaml    what only a human can settle
  policies.yaml          enforced by dbq: blocked columns, mandatory filters, tenant, limits
```

Every fact records where it came from (`fk`, `inferred`, `llm_guess`, `verified`, `human_confirmed`) and a
confidence. The full format is in [`../shared/skills/knowledge-store/SKILL.md`](../shared/skills/knowledge-store/SKILL.md).
