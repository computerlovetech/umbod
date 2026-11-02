---
type: Software Module
title: "Filesystem REST"
description: "Authenticated filesystem browsing, creation, transfers, typed recipient access policies and permanent single-file removal."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [access.py](./access.py) — Shared caller metadata dependency and enriched browse response schemas.
- [deps.py](./deps.py) — Request-local caller and service composition.
- [errors.py](./errors.py) — Safe domain error translation.
- [sharing.py](./sharing.py) — Typed recipient views, explicit recipient-type replacement scopes, policy ETags and eligible-group discovery.
- [deletion.py](./deletion.py) — Authorized permanent file DELETE requiring one strong quoted positive numeric If-Match revision.
- [metadata.py](./metadata.py) — Per-operation node OPTIONS and atomic revision-checked metadata, rename and move PATCH for files and directories.
- [downloads.py](./downloads.py) — Attachment delivery and storage-neutral download response contract.
- [uploads.py](./uploads.py) — Authorized begin, raw PUT, session inspection and idempotent completion routes.
- [upload_transfers.py](./upload_transfers.py) — Capability-only PUT under /api/filesystem; request-local services and no-store success/error responses.
- [models.py](./models.py) — Strict upload requests, single-transfer responses, metadata and child envelopes.
- [routes.py](./routes.py) — Enriched node and browse results, private caller home POST, visible breadcrumbs, directory creation and downloads.

# Related links

- [Capability upload protocol](../../../../../docs/reference/filesystem-upload-transfers.md) — Exact public transfer admission, header credentials and operational limitations.

- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem storage and ownership boundary.
- [ADR-009](../../../../../project/architecture-records/ADR-009-transport-neutral-upload-sessions.md) — Accepted upload contract; abandoned sessions and unreferenced bytes have no automatic cleanup guarantee.
