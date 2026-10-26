---
name: knowledge-promotion
description: Promotion gates for learned knowledge (CI/CD for knowledge). Applies pending proposals from ../learning/proposals/ only if they don't contradict confirmed facts, pass verification on real data, and don't lower accuracy on the eval set; commits promoted changes as one revertible git commit. Use after failure-learner, or when an admin approves a proposal.
---

# Knowledge promotion

A system that learns from feedback can also learn mistakes, or be poisoned on purpose. Nothing enters
`../knowledge/` without passing these gates.

## Gate 0: group and weigh
Group pending proposals that make the same change, and add up their `weight` (user 1, analyst 2,
data_owner 4, admin 5). **One thumbs-up is not proof.**

## Gate 1: contradiction check
The change touches a fact that is `human_confirmed`, has `confidence >= 0.9`, is a declared FK (`source: fk`), or
has `trust: confirmed`, and it disagrees with it?
- If the total weight is below 4 and there is no admin approval: set `status: needs_review`, with the conflict
  in `status_reason`. **Do not overwrite.** The proposal will show up in human-review.
- Otherwise continue.

## Gate 2: verification on real data (run with `../shared/dbq.py`)
| change | must pass |
|---|---|
| add_glossary with sql, add_verified_query | the SQL runs, returns rows, and the result is plausible |
| update_column values | the claimed codes occur in the column |
| update_column unit | the magnitudes are consistent with the unit |
| add_edge | the value overlap is >= 0.9 (relationship-analyst query) |
| add_value_alias | the target value exists in `values.yaml` or in the column |
| lower_edge, add_gotcha, add_synonyms, add_clarification | nothing to run; check that the target table or column exists |

Failure → `status: rejected`, `status_reason: verification failed: ...`.

## Gate 3: apply on a candidate, then run regressions
1. Create a branch: `git switch -c promote-<date>`.
2. Apply all proposals that passed gates 1-2 to the files in `../knowledge/`. The new facts get their trust level:
   - `verified` if gate 2 ran SQL;
   - `confirmed` if the weight is >= 4 or an admin approved it;
   - `proposed` otherwise.
3. Run the db-eval skill on the candidate (sample of 20 verified queries, or all if fewer). Compare with the last
   accuracy in `../learning/eval/`.
4. If accuracy **dropped**: find the proposal responsible by re-running the eval with half of them reverted,
   and repeat on the half that still fails. Reject the culprits (`status_reason: regression`). Keep the rest.

## Commit
- Merge to the main branch as one commit:
  `knowledge: promote N proposals (p-..., p-...) - eval 87% -> 89%`.
- Update each proposal file: `status: promoted`, `promoted_in: <commit sha>`.
- **Rollback** of a bad learning means `git revert <sha>`. Then mark the affected proposals `rejected` with the
  reason.

## Rules
- Every fixed failure becomes a test case: a promoted change for trace X also adds or keeps a verified query
  for X's question (if it has SQL).
- Never let one customer's learnings into another customer's knowledge (separate repo or branch per customer).
