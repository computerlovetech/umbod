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
- [keys.py](./keys.py) — Canonical logical content key validation without host filesystem dependencies.
- [s3_content.py](./s3_content.py) — Immutable S3 byte storage with bounded multipart writes and operation-scoped clients.
- [S3 infrastructure edge](./s3/README.md) — SDK protocols, response validation, provider configuration, and cancellation-safe resource cleanup.

# Related links

- [ADR-014](../../../../../project/architecture-records/ADR-014-s3-content-storage.md) — S3 configuration, credential ownership, streaming, and migration boundaries.
- [ADR-009](../../../../../project/architecture-records/ADR-009-transport-neutral-upload-sessions.md) — Upload publication remains separate from byte storage and transfer instructions.
- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Shared-database namespace and policy storage, independently selected content storage.
- [Filesystem boundary detail](../../../../../project/architecture-records/supporting/filesystem-boundaries.md) — Trusted POSIX directory requirements and byte publication outside database transactions.
- [REST filesystem](../../rest/filesystem/README.md) — Request-scoped authorized content operations over an application-retained content adapter.
