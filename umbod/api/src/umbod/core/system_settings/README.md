---
type: Software Module
title: System Settings
description: Instance-wide settings management, provider group mappings, and effective approval policy.
---

# Files

- [Provider group mappings](./provider_group_mappings/README.md) — Provider values, Umbod group targets, and settings precedence.
- [__init__.py](./__init__.py) — Public settings API and service composition.
- [errors.py](./errors.py) — Management permission and storage failures.
- [models.py](./models.py) — Validated settings, source-aware results, and explicit update inputs.
- [ports.py](./ports.py) — Read and write contracts. Readers return `UNSET` for absent configuration and raise `SettingsStorageUnavailable` for read or validation failures.
- [schema.py](./schema.py) — Backend-neutral singleton schema and settings codec.
- [service.py](./service.py) — Administrator management, approval precedence, and the default-off portable connector flag.
- [store.py](./store.py) — Singleton reads and serialized set and reset transactions.
