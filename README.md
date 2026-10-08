# DB-chatbot

**Turn any AI coding agent into a chatbot for your company database.** It audits your Postgres database once,
writes down what every table means, and then answers business questions with safe, read-only SQL. It keeps
learning from feedback.

Agent-agnostic: the whole system is a set of [Agent Skills](https://agentskills.io) plus one small SQL runner.
It works with **Claude Code, GitHub Copilot (VS Code), OpenAI Codex, Cursor**, or any agent that can read
`AGENTS.md` and run a shell command.

```
you  > What was our net revenue in Munich last quarter?
agent> €184,230 (net of refunds), from 1,912 paid orders.
       SQL: SELECT sum(o.amount - coalesce(r.refunded,0)) / 100.0 ... WHERE s.city = 'Munich' AND ...
       Tables: public.orders, public.refunds, public.stores
       Note: "amount is in EUR cents" was confirmed by your data owner on 2026-10-02.
```

## Why

On real company databases, text-to-SQL rarely fails on SQL syntax. It fails on **missing business context**:
- `amount` is in cents;
- `status = 3` means refunded;
- `orders_old` is dead;
- "clients" means the `accounts` table;
- revenue excludes test customers.

This project treats **the audit and the knowledge it produces as the product**. The chat is the easy part.
The full design is in [`db-chatbot-architecture.md`](db-chatbot-architecture.md).

## How it works

```mermaid
flowchart LR
  subgraph Audit["1 · Onboarding audit"]
    A1[catalog-crawler] --> A2[data-profiler + PII]
    A2 --> A3[relationship-analyst]
    A3 --> A4[domain-clusterer]
    A4 --> A5[table-interpreter<br/>one subagent per domain]
    A4 --> A6[quality-auditor]
    A5 --> A7[knowledge-synthesizer]
    A6 --> A7
    A7 --> A8[knowledge-verifier]
    A8 --> A9[human-review]
  end
  subgraph Store["2 · knowledge/ (git-versioned)"]
    S[overview · domain cards · table & column cards<br/>join graph · glossary/metrics · value index<br/>verified queries · policies]
  end
  subgraph Ask["3 · Answering"]
    Q1[db-answer: route → retrieve → SQL → dbq.py → check → answer]
  end
  subgraph Learn["4 · Continuous learning"]
    L1[feedback-capture] --> L2[failure-learner] --> L3[knowledge-promotion<br/>gates + eval]
    L4[drift-monitor]
  end
  Audit --> Store --> Ask --> L1
  L3 --> Store
  L4 --> Audit
```

- **Code does the deterministic, safety-critical work.** `tools/dbq.py` enforces read-only access, limits,
  filters and PII masking. The agents do the interpretation.
- **Every fact carries its source and confidence.** The sources are `fk`, `inferred`, `llm_guess`, `verified`
  and `human_confirmed`. The bot tells you when an answer relies on a guess.
- **It learns without retraining.** Failures are diagnosed and turned into proposed knowledge changes. The
  changes are checked against real data and regression-tested on an eval set, and only then committed. It works
  like CI/CD, but for knowledge.

## Quickstart

**1. Get the repo** (use a **private** copy per database; see [Privacy](#privacy)).
```bash
git clone https://github.com/adamgdoura6/DB-chatbot.git my-company-db-chat
cd my-company-db-chat
pip install -r requirements.txt
```

**2. Connect a read-only database role.**
```bash
cp .env.example .env        # set DBCHAT_DATABASE_URL=postgresql://ai_reader:...@host:5432/db
python tools/dbq.py "SELECT current_user, version()"
```
Use a dedicated role that has only `SELECT` on the schemas you want covered. Never use an owner or service
key. For example, on Supabase do not use the `service_role` key; it bypasses RLS.

**3. Open the folder in your agent and talk to it.**

| agent | how |
|---|---|
| Claude Code | `claude` in the folder, then: *"Audit my database"* |
| GitHub Copilot (VS Code) | Agent mode in this workspace: *"Audit my database"* |
| Codex | `codex` in the folder: *"Audit my database"* |
| Any other | point it to `AGENTS.md` |

Then ask questions: *"How many active customers do we have?"*, *"Where do we store invoices?"*,
*"Revenue by month this year"*. Give feedback in plain words (*"that's wrong, revenue excludes refunds"*).

**4. Let it learn** (nightly, from cron or CI):
```bash
claude -p "Follow .agents/skills/db-learn/SKILL.md"      # or: codex exec "..."
```

## Repository layout

```
AGENTS.md                     entry point for every agent: intent → skill, non-negotiable rules
CLAUDE.md                     imports AGENTS.md for Claude Code
.agents/skills/<name>/        the skills (SKILL.md + supporting SQL)
tools/dbq.py                  the only database access path (guarded, read-only)
knowledge/                    what the audit learns (filled per database; policies.yaml enforced by dbq)
learning/                     traces, feedback, proposals, eval reports
db-chatbot-architecture.md    the design
```

### Skills

| phase | skills |
|---|---|
| entry points | `db-onboarding`, `db-answer`, `db-learn`, `db-eval`, `human-review`, `drift-monitor` |
| audit | `catalog-crawler`, `data-profiler`, `relationship-analyst`, `domain-clusterer`, `table-interpreter`, `quality-auditor`, `knowledge-synthesizer`, `knowledge-verifier` |
| answering | `knowledge-retrieval`, `sql-review`, `feedback-capture` |
| learning | `failure-learner`, `knowledge-promotion` |
| reference | `knowledge-store` (file formats, provenance, versioning rules) |

## Safety model

Safety is enforced in code, in `tools/dbq.py`, not in prompts:

| protection | how |
|---|---|
| read-only | every statement runs in `BEGIN READ ONLY` with a `statement_timeout`; use a read-only DB role as well |
| SELECT only | parsed with sqlglot: one statement; no writes, DDL, locks, `SELECT INTO` or `EXPLAIN ANALYZE`; dangerous functions blocked (`pg_sleep`, file access, `dblink`, `set_config`, …) |
| restricted data | `blocked_columns` rejected, including via `SELECT *` |
| correct and isolated results | `mandatory_filters` (e.g. soft deletes) and the tenant filter injected into every query |
| load | row cap, timeout, and an `EXPLAIN` cost limit before execution |
| PII | values masked in every output (by column name, value patterns and `pii_columns`) before any model sees them |
| prompt injection via data | the agents have no write tools against the database, and skills treat row content as data |

## Privacy

- `knowledge/` and `learning/` will contain a description of **your** schema and business logic, plus masked
  samples. Keep each database's copy in a **private** repository. Do not open a pull request with them.
- PII is masked before reaching the model, but the schema and aggregate results do reach your agent's model
  provider. Check that this matches your data-processing agreements. For GDPR, use EU-hosted model endpoints if
  needed.

## Status and roadmap

Early stage: Postgres only (including Supabase, RDS and Aurora Postgres).

- [ ] Connection helpers: Supabase read-only role script, AWS cross-account IAM, VPC connector
- [ ] An MCP server version of `dbq` for agents without shell access
- [ ] More engines (MySQL, Snowflake, BigQuery)
- [ ] Pre-built cards for common third-party schemas (Supabase `auth`, Stripe sync, Shopify)
- [ ] Multi-source questions (per-source extractors + DuckDB merge)
- [ ] Example database and end-to-end demo

## Contributing

Contributions are welcome, especially new skills, engine support and real-world gotchas. See
[CONTRIBUTING.md](CONTRIBUTING.md). Report security issues privately (see [SECURITY.md](SECURITY.md)).

## License

[MIT](LICENSE)
