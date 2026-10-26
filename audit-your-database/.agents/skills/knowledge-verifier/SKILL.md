---
name: knowledge-verifier
description: Step 8 of the database audit. Acts as a critic - tests the interpreters' claims against real data (decoded values, units, mandatory filters, metric SQL), adjusts confidence, then generates realistic user questions with SQL, runs them, and keeps the working pairs as verified queries (the eval set). Can run as one parallel subagent per domain.
---

# Knowledge verifier / critic

Assume the cards contain mistakes, and find them with SQL. Run every query through `python ../shared/dbq.py`.

## 1. Test claims
For each table card:
- **Decoded values.** `SELECT <col>::text, count(*) FROM <t> GROUP BY 1 ORDER BY 2 DESC LIMIT 50`.
  - Every claimed code occurs, and every frequent code is decoded: set `source: verified` and
    `confidence >= 0.85`.
  - Otherwise: remove the codes that never occur, lower the confidence, and add an open question for the
    undocumented codes.
- **Units.** Check claims against magnitudes. "Cents" values are integers, typically 100x a plausible price.
  A "seconds" duration should not have a median of 3,600,000. If the data contradicts the claim, fix it or open
  a question.
- **Timestamps.** Check claimed orderings. For example, `paid_at >= created_at` should hold for nearly all rows:
  `SELECT count(*) FILTER (WHERE paid_at < created_at) FROM ...`.
- **Mandatory filters.** Each predicate must run (`SELECT 1 FROM <t> WHERE <pred> LIMIT 1`). Report its
  selectivity: a filter that removes 0% or 100% of rows is suspicious. Remove invalid filters from the card and
  from `policies.yaml`.
- **Joins with fan-out risk.** For 1:N edges used in metrics, make sure the metric SQL aggregates before
  joining.

## 2. Test metrics
Run each `sql` in `glossary.yaml`.
- It runs and gives a plausible result: set `trust: verified`.
- It fails or gives an implausible result (negative revenue, more active users than users): fix it once.
  If it still fails, leave it `proposed` and open a question.

## 3. Generate question → SQL pairs (the eval set)
For each domain, write 5-8 questions a business user would really ask: lookups, counts, aggregates over time,
top-N, joins across 2-3 tables, and a metric. For each one:
1. Write the SQL using only the knowledge cards and glossary, as the db-answer skill would.
2. Run it: `python ../shared/dbq.py --json --max-rows 200 "<sql>"`.
3. Keep it only if it runs, returns rows, and the result is plausible: no column NULL in every row, no
   absurdly large totals from fan-out.
4. Append it to `../knowledge/verified-queries.yaml` with `trust: verified`, `last_verified: <today>` and
   `expected_shape` (e.g. `"12 rows, columns month, revenue_eur"`).

If a question fails because the knowledge is wrong, fix the card, not just the query, and record what changed.

## Output
Updated cards, `glossary.yaml`, `verified-queries.yaml`, `open-questions.yaml`, and `policies.yaml`.
Report the counts, e.g. `claims checked 140 (12 corrected), metrics 9/11 verified, 38 verified queries`.
