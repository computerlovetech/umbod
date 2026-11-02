---
type: Software Module
title: Files infrastructure
description: Filesystem session API, secure raw-byte transfers and in-memory persistence.
---

# Files

- [sharing-route.ts](./sharing-route.ts) — Typed recipient filters, eligible groups and scoped revision-conditioned replacement over shared transport.
- [in-memory-sharing.test-support.ts](./in-memory-sharing.test-support.ts) — Mixed-policy test adapter with filtered reads, scoped replacement and whole-policy revisions.
- [files-api.ts](./files-api.ts) — Browser composition and injectable transport, origin and external transfer fetch.
- [filesystem-route.ts](./filesystem-route.ts) — One-GET browse snapshots, atomic PATCH, on-demand capability checks, conditional deletion and uploads.
- [upload-transfer.ts](./upload-transfer.ts) — Validated raw uploads with endpoint checks and credential-isolated external transfers.
- [in-memory-api.test-support.ts](./in-memory-api.test-support.ts) — Test-only coherent browse snapshots, advisory eligibility, atomic mutations, upload sessions and retained content.
