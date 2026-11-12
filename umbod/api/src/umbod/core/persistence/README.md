---
type: Software Module
title: "Persistence kernel"
description: "Backend-neutral persistence contracts and deferred read planning for bounded-context stores."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [plan.py](./plan.py) — Deferred read plans and results over read-only sessions or write transactions.
- [ports.py](./ports.py) — Read snapshots, primary write transactions, and fail-fast serialized writes with explicit contention errors.
- [query.py](./query.py) — Typed queries, strict range predicates for indexed retention, and explicit non-reusing integer-key schemas.
- [runtime.py](./runtime.py) — Runtime readiness and lifecycle.
- [Generated key contract](../../../../../docs/reference/persistence-generated-keys.md) — Opt-in non-reuse, rollback and existing SQLite schema requirements.
