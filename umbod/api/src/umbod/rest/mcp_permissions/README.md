---
type: Software Module
title: Group permission administration
description: HTTP routes and request-scoped composition for group permission reads and mutations.
---

# Files

- [__init__.py](./__init__.py)
- [assignable_reads.py](./assignable_reads.py) — Catalogue preparation and deferred state reads for assignable targets.
- [dependencies.py](./dependencies.py) — Separate read and mutation composition.
- [routes.py](./routes.py)
- [schemas.py](./schemas.py)
- [mappers.py](./mappers.py)

# Context not available from the code

- [ADR-009](../../../../../project/architecture-records/ADR-009-deferred-read-planning.md) — Why read-model state uses explicit scoped plans instead of implicit query interception.
- [ADR-010](../../../../../project/architecture-records/ADR-010-key-value-storage-drivers.md) — Request-cache ownership and limits on cross-request reuse.
