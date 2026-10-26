---
name: knowledge-retrieval
description: How to find the right context in ../knowledge/<db>/ for a question - candidate tables via cards, synonyms and glossary, real filter values via the value index, join paths via the join graph, and similar verified queries. Used by db-answer and the learning skills.
---

# Knowledge retrieval

Goal: a compact context pack, meaning the 2-8 cards that matter, the join path between them, and matching
values, metrics and examples. Do not load all of `../knowledge/<db>/` for a large database.

## Small database (fewer than ~50 table cards)
Skip searching: read `../knowledge/<db>/overview.md` and all `../knowledge/<db>/tables/*.yaml`, then go to the join path.

## Larger databases
1. **Metrics and examples first.** Search `glossary.yaml` (terms and synonyms) and `verified-queries.yaml`
   (questions) for the question's key words. A matching verified query or metric is the strongest signal.
   Note which tables it uses.
2. **Tables.** Search the table cards for the question's nouns and their likely synonyms. Look at file names,
   `synonyms:`, `summary:`, column names and column `synonyms`. For example:
   `grep -ril -E "customer|client|buyer" ../knowledge/<db>/tables/`.
   Rank tables whose name or synonyms match above tables where only a column matches. Rank `status: legacy`
   last. Read the 3-6 best cards in full.
3. **Values.** For each filter-like word (cities, product names, plan tiers, statuses, countries), search
   `values.yaml`, including `aliases`. Allow case differences and close misspellings ("Munch" → Munich).
   A value hit also tells you which table and column to filter on. If nothing matches, check the data:
   `SELECT DISTINCT col FROM t WHERE col ILIKE '%munich%' LIMIT 10`, unless the column is PII.
4. **Join path.** Connect the chosen tables with `../knowledge/<db>/joins.yaml`:
   - prefer the path with the fewest hops, using high-confidence edges (fk > query_log > inferred > llm_guess);
   - with 3 or more tables, find the smallest connecting tree; tables on the path count as "bridge" tables, so
     read their cards too;
   - note the cardinality of every hop (fan-out risk on 1:N), and any `condition_extra` (polymorphic joins);
   - if no path exists, say so instead of inventing a join.
5. **Domain context.** If the question is broad ("how is billing doing?"), read `../knowledge/<db>/domains/<d>.md`.

## Retrieval diagnostics (for the trace)
Record which tables, metrics and verified queries you retrieved. After answering, note which ones the final SQL
actually used. The learner uses this to tell "the knowledge wasn't found" apart from "the knowledge was wrong".
