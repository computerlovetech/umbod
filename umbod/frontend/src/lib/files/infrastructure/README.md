---
type: Software Module
title: Files infrastructure
description: Filesystem session API, secure raw-byte transfers and in-memory persistence.
---

# Files

- [files-api.ts](./files-api.ts) — Browser composition and injectable transport, origin and external transfer fetch.
- [filesystem-route.ts](./filesystem-route.ts) — Validated browsing and breadcrumb routes, eligibility checks, conditional deletion and upload orchestration.
- [upload-transfer.ts](./upload-transfer.ts) — Validated raw uploads with endpoint checks and credential-isolated external transfers.
- [in-memory-api.ts](./in-memory-api.ts) — Visibility-filtered browsing and breadcrumbs, upload sessions, retained content and idempotent completion without network I/O.
