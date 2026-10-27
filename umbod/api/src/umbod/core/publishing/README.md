---
type: Software Module
title: Publishing
description: Publication reader and writer contracts, events and persisted state.
---

# Files

- [__init__.py](./__init__.py) — Public publication exports.
- [cached.py](./cached.py) — Request-cache publication wrapper.
- [events.py](./events.py) — Publication change messaging events.
- [factories.py](./factories.py) — Persistent publication store composition.
- [store.py](./store.py) — Publication reads, writes and change subscription contracts.
- [stores](./stores/) — Publication persistence and scoped query builders.

# Related links

- [ADR-009](../../../../../project/architecture-records/ADR-009-deferred-read-planning.md) — Scoped bulk publication reads for read models.
- [ADR-010](../../../../../project/architecture-records/ADR-010-key-value-storage-drivers.md) — Request-cache policy and interchangeable storage drivers.
