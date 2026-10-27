---
type: Software Module
title: "Filesystem infrastructure"
description: "Filesystem composition and concrete content storage over the application's shared database."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [config.py](./config.py) — Content storage configuration.
- [factory.py](./factory.py) — Filesystem service and store composition.
- [inmemory.py](./inmemory.py) — In-memory content storage.
- [io.py](./io.py) — Cancellation-safe host I/O.
- [local_content.py](./local_content.py) — Local content storage.
- [objects.py](./objects.py) — Trusted content directory operations.

# Context not available from the code

- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Shared-database namespace and policy storage, independently selected content storage.
- [Filesystem boundary detail](../../../../../project/architecture-records/supporting/filesystem-boundaries.md) — Local content requires trusted POSIX directories; database transactions do not include byte publication. Retired JSON namespaces have no implicit migration.
- [REST filesystem](../../rest/filesystem/README.md) — Implemented browsing and empty creation are separate from planned content operations.
