---
name: db-eval
description: Measures answer quality. Re-asks verified questions through the db-answer process and compares results with the verified SQL (execution accuracy), and computes usage metrics from traces (first-answer success, thumbs-down rate, retries, clarification rate, verified-query share, latency). Use before promoting knowledge changes, after changing skills or models, or when asked how well the bot is doing.
---

# Evaluation

## Execution accuracy (the eval set = verified-queries.yaml)
1. Take every entry with `broken: false`, or a random sample of 20 if there are more. Use a fixed sample when
   comparing two versions, so the comparison is fair.
2. For each entry:
   - Run the expected SQL: `python ../shared/dbq.py --json --max-rows 500 "<expected sql>"`.
   - Answer the **question text only** by following db-answer. **Do not look at the expected SQL.** If your
     agent supports subagents, give each question to a fresh subagent that has not seen
     `verified-queries.yaml` entries for that question.
   - Run the produced SQL the same way.
   - It **passes** if both results hold the same rows: compare the sets of row values, ignoring column names
     and row order, with numbers rounded to 2 decimals.
3. Write `../learning/eval/<timestamp>.md`: accuracy, and a table with question / pass / note (why it failed).
   Append `{"ts": ..., "knowledge_commit": "<git sha>", "accuracy": 0.87, "n": 20}` to
   `../learning/eval/history.jsonl`.

Every failed eval item is a learning signal. Log it as a trace with `rating: -1` from role `eval`, so
failure-learner picks it up.

## Usage metrics (from ../learning/traces and feedback)
| metric | definition |
|---|---|
| first-answer success rate | data questions without negative feedback or a rephrase |
| thumbs-down rate | rating -1 / all ratings |
| retries per question | mean `retries` |
| clarification rate | traces with `clarification` / all |
| verified-query share | final SQL equals (whitespace-insensitive) or is adapted from a verified query |
| latency and cost | if your agent records them |

Report each metric with its trend against the previous report.
