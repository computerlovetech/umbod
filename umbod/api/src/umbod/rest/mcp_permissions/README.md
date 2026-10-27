---
type: Software Module
title: Group permission administration
description: HTTP routes and request-scoped composition for group permission reads and mutations.
---

# Files

- [__init__.py](./__init__.py) — Public HTTP permission exports.
- [assignable_reads.py](./assignable_reads.py) — Catalogue preparation and deferred state reads for assignable targets.
- [dependencies.py](./dependencies.py) — Separate read and mutation composition.
- [routes.py](./routes.py) — Group permission administration endpoints.
- [schemas.py](./schemas.py) — Permission request and response validation.
- [mappers.py](./mappers.py) — HTTP and domain permission conversion.

# Related links

- [ADR-009](../../../../../project/architecture-records/ADR-009-deferred-read-planning.md) — Why read-model state uses explicit scoped plans instead of implicit query interception.
- [ADR-010](../../../../../project/architecture-records/ADR-010-key-value-storage-drivers.md) — Request-cache ownership and limits on cross-request reuse.
