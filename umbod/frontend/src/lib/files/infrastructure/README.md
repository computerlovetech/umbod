---
type: Software Module
title: Files infrastructure
description: Filesystem session API, secure raw-byte transfers and in-memory persistence.
---

# Files

- [sharing-route.ts](./sharing-route.ts) — Node-scoped access inspection, eligible groups and revision-conditioned replacement over shared transport.
- [in-memory-sharing.test-support.ts](./in-memory-sharing.test-support.ts) — Denied-by-default test adapter with explicit sharing configuration and revision checks.
- [files-api.ts](./files-api.ts) — Browser composition and injectable transport, origin and external transfer fetch.
- [filesystem-route.ts](./filesystem-route.ts) — Validated browsing and breadcrumb routes, eligibility checks, conditional deletion and upload orchestration.
- [upload-transfer.ts](./upload-transfer.ts) — Validated raw uploads with endpoint checks and credential-isolated external transfers.
- [in-memory-api.test-support.ts](./in-memory-api.test-support.ts) — Visibility-filtered browsing and breadcrumbs, upload sessions, retained content and idempotent completion without network I/O.
