---
type: Software Module
title: "Key-value infrastructure"
description: "In-memory key-value storage and request-cache composition."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [factory.py](./factory.py) — Driver and cache composition.
- [inmemory.py](./inmemory.py) — In-memory storage adapter.

# Context not available from the code

- [ADR-010](../../../../../project/architecture-records/ADR-010-key-value-storage-drivers.md) — Storage semantics and request-cache lifetime boundary; distributed storage is not implemented.
