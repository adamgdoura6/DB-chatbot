---
name: db-answer
description: Entry point for answering any question about the connected company database - "how many...", "revenue last month", "which customers...", "where do we store invoices?", "what does status 3 mean?". Routes the question, retrieves knowledge, writes and runs one read-only SQL query, checks the result, answers with the SQL and tables used, and logs a trace. Requires a completed audit (../knowledge/<db>/).
---

# Answer a question about the database

Default to **one agent and one final SQL query**: the database is the best join engine there is. Use
subagents only in the special cases at the end.

## 1. Route
Classify the question:
- **schema**: where or how something is stored, what a table or column means, how tables relate. Answer from
  `../knowledge/<db>/` only; no SQL needed. Cite the cards you used.
- **data**: needs numbers or records. Continue below.
- **ambiguous**: no correct answer exists without a choice only the user can make, e.g. "revenue" when gross
  and net both exist and `glossary.yaml` has a `clarify:` for it. Ask the one clarifying question, and stop. A
  missing time range is *not* ambiguous: use all time or an obvious default, and state it.
- **out of scope**: unrelated to this database, or asks to change data (this system is read-only). Decline
  briefly.

Follow-up questions ("and by month?", "only Munich") inherit the previous question and its SQL.

## 2. Retrieve context
Follow the knowledge-retrieval skill. You need the relevant table cards, the join path, matching metrics,
similar verified queries, and real values for any filter words.

## 3. Write the SQL
- If a verified query or metric fits, start from it and adapt it. Do not reinvent it.
- Use only tables and columns that exist in the cards. Prefer canonical tables over legacy ones.
- Apply every gotcha: units (cents → divide by 100.0), statuses, test-data exclusions, timestamp choice.
- Mandatory and tenant filters are injected by `../shared/dbq.py` automatically. Writing them yourself is harmless.
- Watch for join fan-out: aggregate the N side in a subquery before joining when summing.
- Filter on values exactly as they exist (from `values.yaml` or `lookup`), not as the user typed them.
- Before running, check the query against the sql-review skill.

## 4. Execute and check
1. On large tables, check the cost first: `python ../shared/dbq.py --cost "<sql>"`. If `ok` is false, narrow the
   query: indexed filters, a shorter time range, or pre-aggregation.
2. Run it: `python ../shared/dbq.py --json "<sql>"`.
3. Sanity-check the result. Retry at most **3 times** if you see:
   - 0 rows: wrong filter value? wrong join? wrong date range? Check the values with a small query.
   - a column NULL in every row: a wrong join or a wrong column.
   - absurd totals (too big, negative, or more "active users" than users): fan-out or a unit error.
   - a `REJECTED` message from dbq: read the reason and fix the query; never try to get around it.
   Exploratory queries (peeking at 5 rows, checking that a value exists) are fine and don't count as retries.

## 5. Answer
Reply with:
- **The answer first**, in plain language with the key numbers (units converted, values rounded sensibly).
- A small table if there are several rows (at most 20 rows, and say if there are more).
- **SQL used** (the final query) and **tables used**. Showing the SQL builds trust.
- **Assumptions** you made (time range, definition used).
- **A confidence note** if you relied on any `llm_guess` / `proposed` fact or an unanswered open question,
  e.g. "I assumed `amount` is in cents; this hasn't been confirmed yet."

Never state a number that is not in the query result.

## 6. Log the trace
Append one JSON line to `../learning/<db>/traces/<YYYY-MM-DD>.jsonl`:
```json
{"id": "t-<yyyymmddHHMMSS>-<4 random chars>", "ts": "<iso>", "question": "...", "route": "data",
 "retrieved": {"tables": [...], "metrics": [...], "verified_queries": [...]},
 "sql_attempts": ["..."], "errors": ["..."], "final_sql": "...", "tables_used": [...],
 "row_count": 12, "answer": "<first 300 chars>", "assumptions": [...], "low_confidence_facts": [...],
 "retries": 1, "clarification": null}
```
Tell the user they can rate the answer (👍 / 👎 or a correction). Record what they say with the
feedback-capture skill.

## When to use subagents at query time (only these cases)
- **Multi-source questions** (this database plus files or a second database): one extractor per source, then
  merge the extracts locally (e.g. with DuckDB), never by eyeballing.
- **Truly independent sub-questions** that cannot be expressed as one query.
- **Deep analysis** ("why did churn spike in March?"): list 3-6 hypotheses and check each with its own query,
  in parallel subagents if available. Then synthesize, citing the evidence for each finding.
