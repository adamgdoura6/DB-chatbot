---
name: human-review
description: Shows open audit questions and pending knowledge changes to the customer (data owner/admin), records their answers as human_confirmed facts, and produces the weekly knowledge-gaps report. Use after an audit, when the user wants to review or answer questions about their data, or asks what the bot is unsure about.
---

# Human review

A few minutes of a data owner's time fixes more than any agent can. Make it fast for them.

## Show open questions
Read `../knowledge/open-questions.yaml`, take the entries with `answer: null`, and sort them by impact:
- first, questions about columns used in glossary metrics or verified queries;
- then the lowest confidence.

Show them as a numbered list. Each item has the question, your current guess, and why it matters, e.g.:

> 1. **Is `orders.amount` in cents or euros?** My guess: cents (values 990-49900). It affects every revenue number.

Let them answer in any form ("1: cents, 2 yes, skip 3").

## Record answers
For each answer:
1. In `open-questions.yaml`: set `answer`, `answered_by`, and `confidence: 1.0`.
2. Update the fact itself in the table card, glossary or joins: set the value, `source: human_confirmed`,
   `confidence: 1.0`. If the answer contradicts what the card said, fix everything that depended on it:
   glossary SQL, verified queries, gotchas and mandatory filters. Re-run the affected verified queries with
   `../shared/dbq.py`.
3. Commit: `git commit -am "knowledge: human answers to oq-..., oq-..."`.

## Review pending proposals
List `../learning/proposals/*.yaml` with `status: needs_review` (see knowledge-promotion). Show each proposal's
claim, the evidence, and what it would change. On approval, set `approved_by` and run knowledge-promotion for
it. On rejection, set `status: rejected` with the reason.

## Knowledge-gaps report (weekly, or on request)
Write `../learning/gaps-<date>.md` with these sections:
- Open audit questions (top 10 by impact)
- Questions users struggled with (traces with negative feedback, rephrasings, or no final SQL; grouped by
  similar wording)
- Proposals waiting for review
- Broken verified queries (`broken: true`)
- Data-quality warnings (`quality.yaml`, severity warn)
