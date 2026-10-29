---
type: Software Module
title: "Filesystem upload sessions"
description: "Persisted upload staging, authorization and atomic file publication."
---

# Files

- [__init__.py](./__init__.py) — Public upload service and persistence contracts.
- [models.py](./models.py) — Pending, uploaded and completed lifecycle records.
- [ports.py](./ports.py) — Session storage, combined transactions and injectable clock.
- [errors.py](./errors.py) — Expiry, lifecycle conflicts and transfer validation failures.
- [service.py](./service.py) — Bounded immutable transfers and idempotent publication while the published node exists.

# Related links

- [Session persistence](../stores/README.md) — Neutral database storage shared with namespace and ownership.
- [ADR-009](../../../../../../project/architecture-records/ADR-009-transport-neutral-upload-sessions.md) — Accepted contract; abandoned rows and unreferenced bytes persist without automatic reclamation.
