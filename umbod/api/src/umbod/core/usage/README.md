---
type: Software Module
title: Personal usage
description: Owner-scoped MCP completion records, canonical OTEL projection and replay-safe daily rollups.
---

# Files

- [__init__.py](./__init__.py) — Public usage record, ownership, OTEL, and persistence-port contracts.
- [models.py](./models.py) — Immutable records, canonical hashed tool targets, bounded display snapshots, query windows, and summary contracts.
- [ports.py](./ports.py) — Batch persistence, retention and owner-scoped read contracts.
- [ownership.py](./ownership.py) — Trusted issuer/subject ownership resolution.
- [otel.py](./otel.py) — Allowlisted canonical OTEL Logs serialization.
- [retention.py](./retention.py) — One-shot UTC retention with an inclusive retained-day boundary, independent of usage collection.
- [schema.py](./schema.py) — Existing OTEL event ledger plus owner/day outcome and per-tool daily aggregate tables.
- [store.py](./store.py) — Replay-safe background batches, atomic daily counters, indexed retention, and owner/window top-five tool reads.

# Related documentation

- [Persistence boundaries](../../../../../project/architecture-records/ADR-001-backend-neutral-persistence.md) — Application runtime ownership and backend-neutral storage boundaries.
