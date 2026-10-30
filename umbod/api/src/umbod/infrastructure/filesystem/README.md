---
type: Software Module
title: "Filesystem infrastructure"
description: "Filesystem composition and concrete content storage over the application's shared database."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [config.py](./config.py) — Content storage configuration.
- [factory.py](./factory.py) — Filesystem service and store composition, including uploads and direct-node group sharing.
- [inmemory.py](./inmemory.py) — Application-retained content storage with immutable publication and concurrent async reads/writes.
- [io.py](./io.py) — Cancellation-safe host I/O.
- [local_content.py](./local_content.py) — Concurrent local content storage through immutable object publication.
- [objects.py](./objects.py) — Trusted content directory operations.

# Related links

- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Shared-database namespace and policy storage, independently selected content storage.
- [Filesystem boundary detail](../../../../../project/architecture-records/supporting/filesystem-boundaries.md) — Trusted POSIX directory requirements and byte publication outside database transactions.
- [REST filesystem](../../rest/filesystem/README.md) — Request-scoped authorized content operations over an application-retained content adapter.
