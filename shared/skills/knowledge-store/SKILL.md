---
name: knowledge-store
description: Format and rules of the database knowledge store in ../knowledge/<db>/ (overview, domain cards, table and column cards, join graph, glossary and metrics, value index, verified queries, policies, open questions). Read this before reading or writing anything under ../knowledge/<db>/.
---

# Knowledge store

The audit's output is the product. Everything an agent learns about the customer database lives as plain
files under `../knowledge/<db>/`, versioned with git. Every fact records **where it came from** and **how sure we are**.

## Layout

`knowledge/` and `learning/` sit at the repository root, shared by `audit-your-database/` (which writes the
audit) and `talk-to-your-database/` (which reads it and learns). Every path in the skills is written from inside
one of those two folders, hence the `../`. Each database has its own subfolder in both: `<db>` is the active
database's name (`python ../shared/dbq.py --active`). Never read or write another database's folder.

```
../knowledge/<db>/
  database.json                  which database this is the audit of (host, port, name); dbq.py refuses others.
                                 Written by `connect.py --bind`, never by hand
  overview.md                    L0  one page: what the business is, list of domains, cross-cutting caveats
  domains/<domain>.md            L1  tables in the domain, key entities, common questions
  tables/<schema>.<table>.yaml   L2+L3  table card with column cards
  joins.yaml                     join graph (edges)
  glossary.yaml                  business terms + metric definitions (the semantic layer)
  values.yaml                    value index: distinct values of categorical, non-PII columns + aliases
  verified-queries.yaml          question -> SQL pairs (also the eval set)
  policies.yaml                  enforced by ../shared/dbq.py: blocked columns, mandatory filters, tenant, limits
  open-questions.yaml            things only a human can settle
  quality.yaml                   quality flags (legacy, orphans, duplicates, ...)
  _raw/catalog/*.json            catalog snapshot: tables, columns, constraints, indexes, extensions, hashes
  _raw/profiles/<schema>.<table>.json   stats + masked samples (data-profiler)
  _raw/relationships.json        candidate joins with overlap results (relationship-analyst)
../learning/<db>/
  traces/<YYYY-MM-DD>.jsonl      one line per answered question
  feedback.jsonl                 thumbs, corrections, implicit signals
  proposals/<id>.yaml            learner output, waiting for promotion
  eval/<timestamp>.md            eval run reports
```

## Provenance and confidence (on every fact)

`source` is one of:
- `fk`: declared in the catalog
- `inferred`: a code or SQL heuristic, verified on data
- `query_log`: seen in `pg_stat_statements`
- `llm_guess`: interpreted, not yet verified
- `verified`: the claim was tested against real data
- `human_confirmed`: confirmed by the customer

`confidence` is a number from 0 to 1.

Trust levels for glossary entries and queries: `proposed` → `verified` (a SQL test passed) → `confirmed` (an admin
approved it, or several users independently agreed).

When answering, prefer high-confidence facts. **Say so when an answer relies on `llm_guess` or `proposed` facts.**
Never overwrite a `human_confirmed` fact or a `confidence >= 0.9` fact without going through `knowledge-promotion`.

## Table card: `tables/<schema>.<table>.yaml`

```yaml
table: public.orders
domain: billing
status: canonical            # canonical | legacy | test | unknown
summary: One row per checkout attempt, including failed and refunded ones
grain: one row per order
synonyms: [purchases, checkouts]
stats: {rows: 1200000, freshness: "2026-10-08T09:12:00Z", freshness_column: created_at}
key_columns: [id, customer_id, amount, status, created_at]
joins:                       # human-readable copy; joins.yaml is the source of truth
  - "orders.customer_id = customers.id (N:1, fk)"
gotchas:
  - Exclude internal test customers (customers.is_internal = true)
  - Revenue counts status 2 only
mandatory_filters: ["deleted_at IS NULL"]   # also copied into policies.yaml
sensitivity: pii             # none | pii | sensitive
source: llm_guess
confidence: 0.8
columns:
  amount:
    type: bigint
    meaning: total including VAT
    unit: EUR cents
    null_pct: 0
    synonyms: [total, price]
    source: human_confirmed
    confidence: 1.0
  status:
    type: smallint
    meaning: payment state of the order
    values: {1: pending, 2: paid, 3: refunded}
    source: verified
    confidence: 0.95
  email:
    type: text
    pii: email               # values never stored or shown unmasked
```

## `joins.yaml`

```yaml
- left: public.payments
  left_columns: [order_id]
  right: public.orders
  right_columns: [id]
  cardinality: "N:1"          # left:right   1:1 | N:1 | 1:N | N:M
  source: fk                 # fk | inferred | query_log | llm_guess | human_confirmed
  confidence: 1.0
  overlap: 1.0               # share of left values found on the right (inferred edges)
  condition_extra: null      # polymorphic: "commentable_type = 'Order'"
```

## `glossary.yaml`

```yaml
- term: revenue
  synonyms: [sales, turnover]
  definition: Paid orders, net of refunds, in EUR, by payment date
  sql: |
    SELECT sum(amount) / 100.0 AS revenue_eur
    FROM public.orders WHERE status = 2 AND refunded_at IS NULL
  tables: [public.orders]
  trust: verified            # proposed | verified | confirmed
  source: llm_guess
- term: gross vs net revenue
  clarify: "Do you mean gross revenue (incl. refunds) or net revenue?"   # standard clarifying question
```

## `values.yaml`

```yaml
public.stores.city:
  values: [Munich, Berlin, Hamburg]
  aliases: {muc: Munich, münchen: Munich}
public.plans.tier:
  values: [free, premium, enterprise]
```
Never put PII columns here.

## `verified-queries.yaml`

```yaml
- id: vq-0001
  question: How many paid orders did we have last month?
  sql: |
    SELECT count(*) FROM public.orders
    WHERE status = 2 AND created_at >= date_trunc('month', now()) - interval '1 month'
      AND created_at < date_trunc('month', now())
  tables: [public.orders]
  trust: verified
  last_verified: 2026-10-08
  expected_shape: "1 row, 1 column"
  broken: false
```

## `policies.yaml` (read by ../shared/dbq.py, enforced in code)

```yaml
blocked_columns: [public.users.password_hash, public.api_keys.token]
pii_columns: [public.customers.email, public.customers.phone]   # masked in every dbq output
mandatory_filters:
  public.orders: ["deleted_at IS NULL"]
tenant_column: org_id
tenant_tables: [public.orders, public.customers]
max_rows: 1000
statement_timeout_ms: 15000
max_plan_cost: 5000000
```

## `open-questions.yaml`

```yaml
- id: oq-0001
  subject: public.orders.amount
  question: Is amount stored in cents or euros?
  current_guess: EUR cents (values are integers around 1000-50000)
  confidence: 0.6
  answer: null
  answered_by: null
```

## Storage rules
- `knowledge/` and `learning/` are **git-ignored**: customer data never enters the repository, and nothing here
  is committed. There is no history; a learned change is undone from the `previous:` values its proposal records
  (knowledge-promotion).
- Keep files deterministic: sort keys and lists by name, so changes are easy to compare.
- One folder per database. Learnings never cross databases.
