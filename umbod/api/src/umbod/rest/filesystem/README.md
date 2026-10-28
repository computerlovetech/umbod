---
type: Software Module
title: "Filesystem REST"
description: "Authenticated filesystem browsing, directory creation, bounded uploads and attachment downloads."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [deps.py](./deps.py) — Request-local caller and service composition.
- [errors.py](./errors.py) — Safe domain error translation.
- [downloads.py](./downloads.py) — Attachment delivery and storage-neutral download response contract.
- [multipart.py](./multipart.py) — Bounded multipart parsing and temporary-file cleanup.
- [uploads.py](./uploads.py) — Multipart-only single-file upload contract and validation.
- [models.py](./models.py) — Directory inputs, upload policy limits, upload metadata and child envelopes.
- [planned/](./planned/README.md) — Unavailable design-only operations.
- [routes.py](./routes.py) — Browsing, directory creation, upload eligibility, upload and download routes.

# Related links

- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem storage and ownership boundary.
- [Planned contracts](planned/README.md) — Replacement, rename/move, deletion and sharing remain unavailable.
