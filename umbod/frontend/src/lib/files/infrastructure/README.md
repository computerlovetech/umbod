---
type: Software Module
title: Files infrastructure
description: Filesystem session API, secure raw-byte transfers and in-memory persistence.
---

# Files

- [file-content-route.ts](./file-content-route.ts) — Authenticated text and binary preview reads bounded by runtime configuration, with redirects rejected.
- [file-content-route.test.ts](./file-content-route.test.ts) — Content request, cancellation, size limit and outbound node validation tests.


- [sharing-route.ts](./sharing-route.ts) — Node-scoped recipient search, filtered access reads and revision-safe per-item sharing writes.
- [in-memory-sharing.test-support.ts](./in-memory-sharing.test-support.ts) — Test-only scoped policy replacement, namespace-aware visibility and sharing authority checks.
- [files-api.ts](./files-api.ts) — Browser composition and injectable transport, origin and external transfer fetch.
- [filesystem-route.ts](./filesystem-route.ts) — Caller namespace listing, coherent browse snapshots, atomic PATCH, conditional deletion and uploads.
- [upload-transfer.ts](./upload-transfer.ts) — Validated raw uploads with endpoint checks and credential-isolated external transfers.
- [in-memory-api.test-support.ts](./in-memory-api.test-support.ts) — Test-only coherent browse snapshots, advisory eligibility, atomic mutations, upload sessions and retained content.
