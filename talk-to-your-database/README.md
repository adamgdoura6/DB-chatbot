# Talk to your database

Use the AI agent you already have (Claude Code, Codex, GitHub Copilot, Cursor) as a chatbot for your database.
It answers from the audit report in [`../knowledge/<db>/`](../knowledge) and queries the database read-only through
[`../shared/dbq.py`](../shared/dbq.py).

**Needs:** a finished audit (see [`../audit-your-database/`](../audit-your-database)). The agent checks this
and tells you if it's missing.

## Connect your agent

| agent | how |
|---|---|
| Claude Code | in this folder: `claude --add-dir ..` |
| Codex | in this folder: `codex --add-dir ..` |
| GitHub Copilot (VS Code) | open the **repository root** in VS Code, switch Copilot Chat to **Agent** mode, and ask |
| Cursor | open the **repository root**, use Agent mode |
| any other | point it to [`AGENTS.md`](AGENTS.md); it needs to read files and run `python` |

What the agent gets:
- **the audit report**: table and column meanings, joins, metric definitions, real filter values, verified
  queries;
- **the database**: read-only, through `dbq.py` only (SELECT only, row caps, timeouts, PII masked, mandatory and
  tenant filters injected);
- **instructions**: [`AGENTS.md`](AGENTS.md) plus the skills in [`.agents/skills/`](.agents/skills).

`--add-dir ..` gives the agent access to the shared `knowledge/`, `learning/` and `shared/` folders next to this
one. Opening the repository root does the same; the root `AGENTS.md` sends the agent here.

## Ask

```
you  > What was our net revenue in Munich last quarter?
agent> €184,230 (net of refunds), from 1,912 paid orders.
       SQL: SELECT sum(o.amount - coalesce(r.refunded,0)) / 100.0 ... WHERE s.city = 'Munich' AND ...
       Tables: public.orders, public.refunds, public.stores
       Note: "amount is in EUR cents" was confirmed by your data owner on 2026-10-02.
```

Other things to say:
- *"Where do we store invoices?"*, *"What does status 3 mean?"*: answered from the report, no SQL needed
- *"That's wrong, revenue excludes refunds"* or 👍 / 👎: saved as feedback
- *"What are you unsure about?"*: the open questions, ranked by impact
- *"How good are you?"*: runs the eval set

## Let it learn

Feedback becomes proposals in `../learning/<db>/proposals/`. They reach the knowledge only after passing checks on
your data and a regression test. Run the loop nightly (cron or CI):

```bash
cd talk-to-your-database
claude -p "Follow .agents/skills/db-learn/SKILL.md" --add-dir ..
# or: codex exec --add-dir .. "Follow .agents/skills/db-learn/SKILL.md"
```

## Skills in this folder

| skill | job |
|---|---|
| `db-answer` | route → retrieve → write SQL → run via dbq → check → answer with SQL and tables |
| `knowledge-retrieval` | find the right cards, joins, values and example queries |
| `sql-review` | self-check of the SQL before it runs |
| `feedback-capture` | record 👍 / 👎 / corrections |
| `db-learn` | nightly loop: drift check → failure-learner → knowledge-promotion → gaps report |
| `failure-learner` | diagnose failures, write proposals |
| `knowledge-promotion` | gates: no contradiction, verified on data, no eval regression |
| `db-eval` | accuracy on the verified-query set |
