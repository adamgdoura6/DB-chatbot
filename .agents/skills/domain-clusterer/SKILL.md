---
name: domain-clusterer
description: Step 4 of the database audit. Groups tables into business domains (billing, users, inventory, auth, legacy...) using the join graph, then names each domain. Produces the domain assignment that the table-interpreter runs on. Use after relationship-analyst.
---

# Domain clusterer

Group tables by **how they connect**, not by how they are named. Use naming only to break ties.

## Procedure
1. Build the graph: tables are nodes, and edges come from `knowledge/joins.yaml`. Weight each edge by its
   confidence. Ignore edges to very generic hub tables when deciding clusters. For example, nearly everything
   joins to `users` or `organizations`; such a hub belongs to its own domain (e.g. `accounts`), not to every
   domain.
2. Find the connected groups. Split a large group (more than ~25 tables) where the joins between its parts are
   sparse. Each part should be a set of tables that are mostly joined to each other.
3. Tables with no joins: group them by schema and name prefix (`audit_*`, `tmp_*`, `stripe_*`). Put anything
   that looks temporary or legacy into a `legacy` domain.
4. Separate schemas are usually separate domains (e.g. Supabase `auth`, `storage`). Third-party synced schemas
   (Stripe, Shopify, HubSpot exports) each get their own domain.
5. Name each domain in short snake_case after the business area it covers: `billing`, `customers`, `catalog`,
   `inventory`, `auth`, `analytics`, `support`, `legacy`. Names must be unique.

## Output
Write one file per domain, `knowledge/domains/<domain>.md`, holding for now only the table list:

```markdown
# Domain: billing

Tables: public.orders, public.order_items, public.payments, public.refunds, public.invoices
```
The knowledge-synthesizer fills in the rest later. Report the domains in one line each:
`billing (5): orders, order_items, payments, refunds, invoices`.

For large schemas (more than about 300 tables), cluster schema by schema and keep each domain under ~25 tables,
so a single table-interpreter can hold a whole domain in context.
