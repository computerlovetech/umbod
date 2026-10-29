---
type: Software Module
title: "Filesystem"
description: "Storage-independent filesystem operations with separate authorization and persistence modules."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [administration/](./administration/README.md) — Trusted root group policy editing.
- [authorization/](./authorization/README.md) — Identity resolution and permission decisions.
- [browsing/](./browsing/README.md) — Caller-aware summaries, child listing and transaction-consistent visible breadcrumbs.
- [content/](./content/README.md) — Authorized streaming uploads and downloads.
- [creation/](./creation/README.md) — Authorized node creation.
- [deletion/](./deletion/README.md) — Authorized permanent single-file removal without byte deletion.
- [errors.py](./errors.py) — Namespace and storage failures.
- [models.py](./models.py) — Nodes, metadata and access policy.
- [namespace.py](./namespace.py) — Pure namespace rules.
- [ports.py](./ports.py) — Namespace, content and policy contracts.
- [provisioning/](./provisioning/README.md) — Trusted one-time root bootstrap.
- [service.py](./service.py) — Raw filesystem coordination.
- [stores/](./stores/README.md) — Database-neutral namespace and policy stores.
- [transactions.py](./transactions.py) — Combined namespace and policy transactions.
- [uploads/](./uploads/README.md) — Persisted upload lifecycle and atomic publication.

# Related links

- [Filesystem infrastructure](../../infrastructure/filesystem/README.md) — Configured composition and concrete content adapters under ADR-006.
- [Filesystem acceptance tests](../../../../tests/umbod/core/filesystem/) — Namespace, authorization and persistence acceptance coverage.
