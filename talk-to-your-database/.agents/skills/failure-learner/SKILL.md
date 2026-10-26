---
name: failure-learner
description: Offline learner (run nightly/hourly, never during a user's question). Reviews failed, corrected and positively rated traces, diagnoses the root cause of each failure, and writes concrete proposed knowledge changes with evidence to ../learning/<db>/proposals/. Never edits ../knowledge/<db>/ directly.
---

# Failure learner

The system learns by improving its **knowledge**, not by retraining models. Each failure → a diagnosis → a
specific, testable proposed fix.

## 1. Collect cases
From `../learning/<db>/traces/*.jsonl` and `../learning/<db>/feedback.jsonl`, skip traces already cited as `evidence` in any
`../learning/<db>/proposals/*.yaml`. Then collect:
- **Failures:** `rating: -1`, any correction or corrected SQL, `implicit: rephrased`, data questions with no
  `final_sql`, `retries >= 3`, or guard rejections that ended the answer.
- **Successes:** `rating: 1` (or `implicit: used`) with a `final_sql`. These become candidate verified queries.

## 2. Diagnose each failure
Re-read the trace, the cards it retrieved and used, and the feedback. Reproduce the problem with
`../shared/dbq.py` if useful. Pick **one** root cause:

| root cause | typical sign | proposed change |
|---|---|---|
| unknown_term | user word not in the glossary or synonyms ("clients", "MRR") | `add_glossary` or `add_synonyms` |
| wrong_meaning | unit, enum or timestamp misread | `update_column` + `add_gotcha` |
| wrong_join | wrong path, fan-out, polymorphic type ignored | `lower_edge` + `add_edge` |
| not_retrieved | the right card existed but wasn't in `retrieved` | `add_synonyms` (user's words on that card) |
| wrong_metric | definition doesn't match what the business means | `add_glossary` (corrected definition and SQL) |
| value_not_found | "Muc" vs "Munich", no value hit | `add_value_alias` |
| ambiguous_question | two valid readings, the user had to correct the choice | `add_clarification` |
| sql_generation_error | knowledge was right, the SQL was wrong | `add_verified_query` (corrected) |
| not_a_failure | the answer was right; the user's expectation was off | no change (record it as reviewed) |

Prefer the **smallest** change that would have produced the right answer. If the user's correction itself looks
wrong given the data, still record it, but say so in `explanation`.

## 3. Write proposals
One file per change, `../learning/<db>/proposals/p-<yyyymmdd>-<n>.yaml`:
```yaml
id: p-20261008-3
status: pending            # pending | promoted | rejected | needs_review
root_cause: wrong_meaning
explanation: User said revenue must exclude refunds; current metric sums all paid orders incl. later refunds.
evidence: [t-20261007142211-ab3f]
weight: 4                  # sum of feedback weights: user 1, analyst 2, data_owner 4, admin 5
change:
  type: add_glossary       # add_glossary | update_column | add_gotcha | add_synonyms | lower_edge | add_edge
                           # | add_value_alias | add_verified_query | add_clarification
  term: revenue
  definition: Paid orders minus refunded amounts, EUR, by paid_at
  sql: |
    SELECT sum(o.amount - coalesce(r.refunded, 0)) / 100.0 AS revenue_eur
    FROM public.orders o
    LEFT JOIN (SELECT order_id, sum(amount) AS refunded FROM public.refunds GROUP BY 1) r ON r.order_id = o.id
    WHERE o.status = 2
  synonyms: [net revenue]
```
Other change shapes use the fields they need: `table`, `column`, `meaning`, `unit`, `values`, `text`, `left`,
`left_columns`, `right`, `right_columns`, `alias`, `value`, `question`, `clarify`.

Each success becomes an `add_verified_query` proposal, with its question and final SQL, and its weight.

## 4. Report
Give counts per root cause. Also add them to `../learning/<db>/learner-stats.jsonl` as
`{"date": ..., "counts": {...}}`. Aggregated root-cause counts show which prompts and skills need improving.
