---
type: Software Module
title: "Filesystem REST"
description: "Authenticated filesystem browsing, creation, transfers, direct-node group sharing and permanent single-file removal."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [deps.py](./deps.py) — Request-local caller and service composition.
- [errors.py](./errors.py) — Safe domain error translation.
- [sharing.py](./sharing.py) — Node-authorized eligible-group metadata, inspection and replacement with opaque policy ETags and strict group inputs.
- [deletion.py](./deletion.py) — Authorized OPTIONS and permanent file DELETE requiring one strong quoted positive numeric If-Match revision.
- [downloads.py](./downloads.py) — Attachment delivery and storage-neutral download response contract.
- [uploads.py](./uploads.py) — Authorized OPTIONS, begin, raw PUT, inspection and idempotent completion routes.
- [models.py](./models.py) — Strict upload requests, single-transfer responses, metadata and child envelopes.
- [planned/](./planned/README.md) — Unavailable design-only operations.
- [routes.py](./routes.py) — Browsing, minimal visible breadcrumbs, directory creation and download routes.

# Related links

- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem storage and ownership boundary.
- [ADR-009](../../../../../project/architecture-records/ADR-009-transport-neutral-upload-sessions.md) — Accepted upload contract; abandoned sessions and unreferenced bytes have no automatic cleanup guarantee.
- [Planned contracts](planned/README.md) — Content replacement, rename/move and owned/shared listing remain unavailable.
