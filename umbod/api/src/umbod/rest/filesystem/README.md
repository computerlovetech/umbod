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
- [sharing.py](./sharing.py) — Typed recipient views, explicit recipient-type replacement scopes, policy ETags and unified recipient search.
- [deletion.py](./deletion.py) — Authorized permanent file DELETE requiring one strong quoted positive numeric If-Match revision.
- [metadata.py](./metadata.py) — Per-operation node OPTIONS and atomic revision-checked metadata, rename and move PATCH for files and directories.
- [downloads.py](./downloads.py) — Private temporary storage redirects and streamed attachments with deterministic source cleanup.
- [uploads.py](./uploads.py) — Authorized S3-direct or API-transfer begin, no-store session instructions and idempotent verified completion.
- [upload_transfers.py](./upload_transfers.py) — Capability-only PUT under /api/filesystem; request-local services and no-store success/error responses.
- [models.py](./models.py) — Strict upload requests, explicit transfer authorization and unavailable descriptors, metadata and child envelopes.
- [routes.py](./routes.py) — Enriched browsing, private caller homes, directory creation and auto/explicit-stream content delivery.

# Related links

- [Capability upload protocol](../../../../../docs/reference/filesystem-upload-transfers.md) — Exact public transfer admission, header credentials and operational limitations.

- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem storage and ownership boundary.
- [ADR-009](../../../../../project/architecture-records/ADR-009-transport-neutral-upload-sessions.md) — Accepted upload contract; abandoned sessions and unreferenced bytes have no automatic cleanup guarantee.
