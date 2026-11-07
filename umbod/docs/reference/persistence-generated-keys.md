---
type: Persistence Contract
title: Generated integer keys
description: Explicit non-reuse guarantees for sequence and cursor tables, including rollback and existing SQLite schemas.
---

# Generated integer keys

## Opt-in non-reuse

`NonReusingIntegerKeyCodec` declares one integer primary key whose automatically generated values must exceed its committed historical maximum. Messaging events use this policy; ordinary `KeyCodec` tables do not promise historical non-reuse.

Deletion never resets an opted-in table's allocation history. Successful explicit inserts and upserts also advance its high-water mark. Allocation is table-local and transactional. Rolled-back allocations may be reused; consecutive or gapless values are not guaranteed. The policy governs automatic allocation, not whether callers may explicitly reinsert a chosen key.

In-memory history lasts for the database runtime. SQLite history survives reopening and application readiness. Registration binds the policy to the table identity; an ordinary descriptor cannot downgrade an already opted-in table. Schema descriptors include the policy so deferred read planning does not treat different allocation contracts as equivalent.

An existing ordinary table cannot be opted in merely by replacing its descriptor. Its missing history requires an explicit migration or a fresh in-memory database. Conflicting schema preparation is atomic.

## Existing SQLite storage

Opted-in tables require an integer primary key backed by SQLite `AUTOINCREMENT`. Existing compliant tables are retained, including their historical sequence state; preparation must not rebuild them or reset that state.

An incompatible existing table fails preparation with an explicit migration requirement. No automatic rebuild or inferred historical watermark is provided. Deleted values from a plain integer-key table cannot be recovered from its surviving rows. A context-owned migration must establish an authoritative historical watermark or an explicitly approved guarantee cutover before enabling non-reuse.

## Boundaries

The neutral schema declares the guarantee. Drivers implement it; SQLite-specific schema validation remains in infrastructure. Tests exercise public database operations for allocation behavior and reserve physical schema checks for SQLite adapter tests.

- [SQLite allocation rules](https://www.sqlite.org/autoinc.html) — Committed historical maxima, rollback and `AUTOINCREMENT` limitations.
