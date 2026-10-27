---
type: Software Module
title: Request caching
description: Operation-owned asynchronous cache policy over an injected key-value driver.
---

# Files

- [__init__.py](./__init__.py) — Public cache exports.
- [errors.py](./errors.py) — Recursive cache load failures.
- [models.py](./models.py) — Namespaced storage keys and generations.
- [ports.py](./ports.py) — Asynchronous request-cache contract.
- [request_cache.py](./request_cache.py) — Concurrent loading and request-local invalidation.

# Related links

- [ADR-010](../../../../../project/architecture-records/ADR-010-key-value-storage-drivers.md) — Driver ownership, logical invalidation and constraints on future remote storage.
