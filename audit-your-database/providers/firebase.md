# Firebase

**Status: planned.**

## Why not yet
Firestore and the Realtime Database are document stores. They have no SQL, no system catalog, no declared
columns, types or foreign keys. The audit is built on reading the Postgres catalog and profiling with SQL, and the
chatbot answers by writing guarded SQL. Firestore support needs its own pieces:

- a schema sampler that infers "tables" (collections and subcollections) and fields from sampled documents;
- relationship detection from reference fields and id-shaped strings;
- a read-only query runner with the same guarantees as `shared/dbq.py` (limits, PII masking), using Firestore
  queries instead of SQL.

## What works today
- **Firebase Data Connect** stores its data in Cloud SQL for PostgreSQL: connect it as
  [any other PostgreSQL](postgres.md).
- **Firestore → BigQuery export** (the *Stream Firestore to BigQuery* extension) gives you a SQL copy. It will
  work once BigQuery support lands.

If you need Firestore support, open an issue with your use case.
