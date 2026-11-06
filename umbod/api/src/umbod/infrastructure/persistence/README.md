---
type: Software Module
title: "Persistence infrastructure"
description: "Database driver composition, schema readiness and explicit legacy personal-discovery preparation."
---

# Files

- [runtime.py](./runtime.py) — Application-scoped backend selection, eager SQLite pool startup, schema readiness and draining shutdown.
- [schema_preparation.py](./schema_preparation.py) — Application table registration and group reconciliation.
- [personal_discovery.py](./personal_discovery.py) — Bootstrap-only missing owner projections with per-owner conditional transactions.
- [group_reconciliation.py](./group_reconciliation.py) — Persisted group catalogue reconciliation.
- [inmemory/](./inmemory/) — In-memory database adapter.
- [sqlite/](./sqlite/README.md) — Provider-injected SQLite adapter, backend-local resource factories and transactional metadata upgrades.
