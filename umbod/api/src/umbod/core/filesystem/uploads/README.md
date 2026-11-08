---
type: Software Module
title: "Filesystem upload sessions"
description: "Persisted upload staging, authorization and atomic file publication."
---

# Files

- [__init__.py](./__init__.py) — Public upload service and persistence contracts.
- [models.py](./models.py) — Legacy-compatible receipts, checksums, delegated claims and server-owned external transfer keys and deadlines.
- [ports.py](./ports.py) — Session storage, combined transactions, injectable clock and validated external transfer capability.
- [errors.py](./errors.py) — Expiry, lifecycle conflicts and transfer validation failures.
- [service.py](./service.py) — Internal streaming, external readback verification outside transactions, bounded authority and atomic idempotent publication.

# Related links

- [Capability upload protocol](../../../../../../docs/reference/filesystem-upload-transfers.md) — Transfer deadlines, completion and crash-recovery limitations.

- [Session persistence](../stores/README.md) — Neutral database storage shared with namespace and ownership.
- [ADR-009](../../../../../../project/architecture-records/ADR-009-transport-neutral-upload-sessions.md) — Accepted contract; abandoned rows and unreferenced bytes persist without automatic reclamation.
