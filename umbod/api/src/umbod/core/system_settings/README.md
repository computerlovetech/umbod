---
type: Software Module
title: System Settings
description: Instance-wide settings management and effective approval policy.
---

# Files

- [__init__.py](./__init__.py) — Public settings API and service composition.
- [errors.py](./errors.py) — Management permission and storage failures.
- [models.py](./models.py) — Validated settings, source-aware results, and explicit update inputs.
- [ports.py](./ports.py) — Read and write contracts. Readers return `UNSET` for absent configuration and raise `SettingsStorageUnavailable` for read or validation failures.
- [schema.py](./schema.py) — Backend-neutral singleton schema and settings codec.
- [service.py](./service.py) — Administrator management, override precedence, and fail-closed policy lookup.
- [store.py](./store.py) — Singleton reads and serialized set and reset transactions.
