---
type: Software Module
title: "Persistence infrastructure"
description: "Database driver composition and schema readiness."
---

# Files

- [runtime.py](./runtime.py) — Application-scoped backend selection, eager SQLite pool startup, schema readiness and draining shutdown.
- [schema_preparation.py](./schema_preparation.py) — Application table registration, including personal usage ledger and rollups, and group reconciliation.
- [group_reconciliation.py](./group_reconciliation.py) — Persisted group catalogue reconciliation.
- [inmemory/](./inmemory/) — In-memory database adapter.
- [sqlite/](./sqlite/README.md) — Provider-injected SQLite adapter, backend-local resource factories and transactional metadata upgrades.
