---
name: db-learn
description: Entry point for the continuous-learning loop - runs failure-learner, knowledge-promotion (with db-eval regression gate), drift-monitor and the knowledge-gaps report in order. Use on a schedule (e.g. nightly) or when the user asks the bot to learn from recent feedback.
---

# Continuous learning loop

Never run this while answering a user's question. It is an offline job.

1. **Drift first.** Follow drift-monitor, section 1 (schema changes). This way learnings are applied to the
   current schema.
2. **Learn.** Follow failure-learner. It turns new failed, corrected and liked traces into proposals.
3. **Promote.** Follow knowledge-promotion. It runs the contradiction check, verification on data, and the
   db-eval regression gate, then commits.
4. **Refresh.** If it is the weekly run, also follow drift-monitor sections 2-4.
5. **Report.** Follow human-review → knowledge-gaps report. Tell the user:
   - number of proposals: promoted, rejected, needing review;
   - the accuracy change;
   - the top 3 open questions for a human;
   - broken verified queries.

## Scheduling
Any scheduler can run this with any agent CLI that has the repository checked out. Examples:
- Claude Code: `claude -p "Follow .agents/skills/db-learn/SKILL.md"`
- Codex: `codex exec "Follow .agents/skills/db-learn/SKILL.md"`
- or a CI job running one of the above nightly.
