---
type: Software Module
title: Portable draft validation
description: Owner-scoped compatibility checks for immutable portable connector revisions.
---

# Files

- [service.py](./service.py) — Validate the requested saved revision only after the author check, with bounded service concurrency.
- [models.py](./models.py) — Revision-tagged results, per-stage status, and bounded source diagnostics.
- [ports.py](./ports.py) — Draft compatibility inspection and service-unavailability boundary.
- [Monty adapter](../../../../infrastructure/portable_connectors/README.md) — Offline checks without running the declared handlers or granting HTTP access.
