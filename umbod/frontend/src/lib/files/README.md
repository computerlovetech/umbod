---
type: Software Module
title: "User files"
description: "User filesystem browsing, directory creation, authorized uploads and single-file deletion."
---

# Files

- [api.ts](./api.ts) — Filesystem browsing, authoritative breadcrumbs and mutation port.
- [breadcrumbs-api.test.ts](./breadcrumbs-api.test.ts) — Minimal breadcrumb schemas, visibility boundaries and shared HTTP transport tests.
- [state/navigation-state.svelte.ts](./state/navigation-state.svelte.ts) — Independent path reads, confirmed parent navigation and known-ancestor overflow state.
- [state/navigation-state.test.ts](./state/navigation-state.test.ts) — Deep links, partial paths, stale responses, disposal, ancestor overflow and read isolation tests.
- [domain/](./domain/) — Filesystem validation contracts.
- [errors.ts](./errors.ts) — Safe read, creation and upload failures.
- [state/deletion-state.svelte.ts](./state/deletion-state.svelte.ts) — File eligibility, confirmation, revision capture and safe deletion reconciliation.
- [state/row-deletion-state.svelte.ts](./state/row-deletion-state.svelte.ts) — Retained row controllers, incremental bounded eligibility checks and cancellation/error/removal focus recovery.
- [state/row-deletion-state.test.ts](./state/row-deletion-state.test.ts) — Concurrent deletion, upload-to-delete eligibility, reconciliation, navigation safety and focus tests.
- [state/deletion-state.test.ts](./state/deletion-state.test.ts) — Cancellation, stale responses, duplicate prevention and recovery tests.
- [deletion-api.test.ts](./deletion-api.test.ts) — Conditional file deletion and eligibility boundary tests.
- [files-api.test.ts](./files-api.test.ts) — Filesystem port and HTTP tests.
- [upload-session.test.ts](./upload-session.test.ts) — Upload phases, retained bytes, descriptor validation and credential isolation tests.
- [fixtures.test-support.ts](./fixtures.test-support.ts) — Test-only node fixtures.
- [Infrastructure](./infrastructure/README.md) — Filesystem HTTP, session transfers and in-memory adapters.
- [state/](./state/) — URL selection, page drops, upload eligibility and mutation state.

# Architecture

- [ADR-009: Transport-Neutral Upload Sessions](../../../../project/architecture-records/ADR-009-transport-neutral-upload-sessions.md) — Accepted upload session and transfer boundary contract.
- [ADR-006: Filesystem Infrastructure Boundary](../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem ownership and storage authority.
