---
name: knowledge-synthesizer
description: Step 7 of the database audit. Writes the top layers of the knowledge store from the table cards - the one-page database overview (L0), domain cards (L1), and the glossary of business terms and metric definitions with exact SQL (the semantic layer). Use after table-interpreter and quality-auditor.
---

# Knowledge synthesizer

## 1. Domain cards: `../knowledge/domains/<domain>.md`
For each domain, read its table cards and write:

```markdown
# Domain: billing

Everything about money coming in: orders, their line items, payments and refunds.

Tables: public.orders (canonical), public.order_items, public.payments, public.refunds, public.orders_old (legacy)

Key entities: order (one checkout), payment (one capture attempt), refund

How the tables connect: orders 1:N order_items; orders 1:N payments; payments 1:N refunds

Common questions:
- Revenue per month / per store / per product
- Refund rate
- Average order value
- Failed payment rate

Watch out: amounts are EUR cents; revenue = status 2 minus refunds; exclude internal customers.
```

## 2. Overview: `../knowledge/overview.md` (L0, at most one page)
- What the business is and does, as far as the data shows.
- The list of domains, each with one line.
- Cross-cutting caveats: currencies, time zones, multi-tenancy (`org_id`), test data, legacy areas.
- The audit scope: schemas included and date of the audit.

## 3. Glossary and metrics: `../knowledge/glossary.yaml`
Define the business terms users will say, mapped to exact SQL. Examples: revenue, order, customer, active user,
churn, MRR, AOV, conversion, refund rate.

For each term:
- `definition` states the choices explicitly: gross or net, refunds included or not, which timestamp, which
  statuses, and test rows excluded.
- `sql` is a complete PostgreSQL `SELECT` over all time. It uses schema-qualified tables, applies the gotchas
  and mandatory filters, and converts units.
- `synonyms` are the user words for it. `tables` lists the tables involved.
- Set `trust: proposed`, `source: llm_guess`. The knowledge-verifier upgrades the entry after testing it.
- If a term has two reasonable definitions and the data cannot decide between them (e.g. gross vs net revenue),
  add a `clarify:` entry with the standard question to ask the user. Also add an open question for the data
  owner.

Only define metrics the schema can actually support. Prefer canonical tables over legacy ones.
