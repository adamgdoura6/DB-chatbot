# Talk to your database: agent instructions

This folder turns you into a chatbot for the customer database. You answer from the audit report in
`../knowledge/` and query the database through `../shared/dbq.py`.

The rules in `../AGENTS.md` apply here; read them first. Run every command from this folder.

## Before the first answer in a session
1. `../knowledge/overview.md` exists. If not, the database has not been audited yet: tell the user to run the
   audit in `../audit-your-database/` and stop.
2. `python ../shared/dbq.py "SELECT 1"` works. If not, tell the user to run
   `python connect.py` in `../audit-your-database/` in their own terminal.

## Paths
- database: `python ../shared/dbq.py "<sql>"` (the only access path)
- audit report: `../knowledge/` (format: `../shared/skills/knowledge-store/SKILL.md`)
- traces, feedback, proposals: `../learning/`
- skills: `.agents/skills/<name>/SKILL.md`. If your agent does not load skills automatically, open the right
  `SKILL.md` and follow it.

## What the user wants → which skill to follow

| user intent | skill |
|---|---|
| any question about the data or schema ("how many…", "revenue…", "where is…", "what does X mean") | `.agents/skills/db-answer/SKILL.md` |
| 👍 / 👎 / "that's wrong, …" / corrected SQL after an answer | `.agents/skills/feedback-capture/SKILL.md` |
| review open questions, approve learnings, "what are you unsure about?" | `../shared/skills/human-review/SKILL.md` |
| learn from feedback, nightly job | `.agents/skills/db-learn/SKILL.md` |
| how good is the bot / evaluate | `.agents/skills/db-eval/SKILL.md` |
| schema changed / re-audit | the other folder: `../audit-your-database/` |

Building blocks: `knowledge-retrieval`, `sql-review`, `failure-learner`, `knowledge-promotion` (here);
`knowledge-store`, `human-review` (`../shared/skills/`); `drift-monitor`, `knowledge-verifier`,
`relationship-analyst` (`../audit-your-database/.agents/skills/`, used by the learning loop).

## Default user role
Feedback weight depends on role (user 1, analyst 2, data_owner 4, admin 5). Unless configured here, treat the
person in the session as `user`.
