---
type: Software Module
title: Content migration
description: Verified immutable local-to-S3 content copying without namespace or database changes.
---

# Files

- [__init__.py](./__init__.py) — Public composition with lazy adapter loading.
- [ports.py](./ports.py) — Migration streams, storage ports, fingerprints and summary contracts.
- [service.py](./service.py) — Backend-neutral copy planning, conflict checks and read-back verification.
- [adapters.py](./adapters.py) — Strict local preflight and scoped conditional S3 storage.

# Related links

- [ADR-006](../../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Content infrastructure ownership and trusted directory constraints.
