---
type: Software Module
title: Agent behaviour
description: Published behaviour patterns, collection playbooks and acknowledged agent self-reports with bounded retention.
---

# Files

- [__init__.py](./__init__.py) — Public domain contracts, errors and service factory.
- [defaults.py](./defaults.py) — Built-in patterns and requested-only reporting instructions, seeded once for new configurations.
- [models.py](./models.py) — Immutable configuration, instruction, assessment, receipt and report contracts.
- [ports.py](./ports.py) — Atomic configuration and report persistence boundary.
- [policy.py](./policy.py) — Caller eligibility, pattern selection, reporting safeguards and canonical deduplication.
- [errors.py](./errors.py) — Safe domain failure codes and publication conflicts.
- [service.py](./service.py) — Application operations with injected storage, clock and identity generation.
- [factory.py](./factory.py) — Shared database composition with UTC time and random report identifiers.
- [schema.py](./schema.py) — Backend-neutral configuration, report and receipt tables.
- [store.py](./store.py) — Serialized publication, deduplicated reporting, filtering, deletion and expiry.
- [retention.py](./retention.py) — One-shot batched report and receipt expiration for the explicitly composed cleanup runner.

# Related links

- [Persistence](../persistence/README.md) — Application-scoped database and transaction ports.
- [Signals](../signals/README.md) — Internal optional observation, distinct from durable diagnostic reports.
