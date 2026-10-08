# Contributing

Thanks for helping. This project is mostly **instructions for agents** (skills) plus one small, safety-critical
script, so contributions look a bit different from a typical code project.

## Ground rules
- **Never commit real customer data.** That includes `knowledge/` contents, traces, feedback, connection
  strings, or masked samples from a real database. Examples must be invented.
- **Safety lives in `tools/dbq.py`, not in prompts.** Changes that weaken a guard (allowing writes, removing
  masking, adding bypass flags) will not be accepted. Changes that strengthen a guard are very welcome.
- **Stay agent-agnostic.** Skills must work for any agent that can read Markdown and run a shell command. Do not
  depend on one vendor's tool names. Where a feature differs between agents (e.g. subagents), describe the
  behaviour and a fallback.

## Writing or changing a skill
- One folder per skill: `.agents/skills/<name>/SKILL.md`, following the [Agent Skills](https://agentskills.io)
  format.
  - Frontmatter `name` matches the folder name (lowercase letters, digits and hyphens).
  - `description` says **what the skill does and when to use it**, in at most 1024 characters.
- Keep each skill to one job, with clear inputs and outputs on disk (see `knowledge-store`).
- Prefer prepared SQL files and exact procedures over vague guidance. Deterministic steps should be as close to
  "run this, save that" as possible.
- If you add an entry-point skill, add it to the intent table in `AGENTS.md` and to the README.

## Changing `tools/dbq.py`
- Standard library plus `psycopg`, `sqlglot` and `PyYAML` only.
- Check the guard offline with `--check` (no database needed), e.g.:
  ```bash
  python tools/dbq.py --check "DELETE FROM t"        # must be rejected (exit code 2)
  python tools/dbq.py --check --file .agents/skills/catalog-crawler/queries/tables.sql   # must pass
  ```
- Describe in the PR what you tested: which queries are now rejected or allowed.

## Pull requests
1. Fork, create a branch, and make focused changes.
2. Explain the problem and how the change fixes it. For skill changes, include a short example run
   (anonymised) with any agent.
3. Be kind in reviews. By contributing, you agree that your work is licensed under the MIT license.
