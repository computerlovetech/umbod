---
type: Software Module
title: "User files"
description: "User filesystem browsing, scoped group and user sharing, directory creation, uploads and file deletion."
---

# Files

- [state/drag-move-state.svelte.ts](./state/drag-move-state.svelte.ts) — Internal file drags, cursor previews, staged move reviews, cancellation, move feedback and focus recovery.
- [state/drag-move-state.test.ts](./state/drag-move-state.test.ts) — Transfer validation, move eligibility, cancellation, uncertain outcomes and navigation-race tests.
- [state/row-editing-state.svelte.ts](./state/row-editing-state.svelte.ts) — Per-row editing controllers with browse-seeded eligibility, bounded checks for new rows and retained drafts.
- [state/row-editing-state.test.ts](./state/row-editing-state.test.ts) — Child targeting, reconciliation, concurrency limits and stale lifecycle tests.
- [state/node-update-state.svelte.ts](./state/node-update-state.svelte.ts) — Rename and shared picker/native move reviews, explicit confirmation, cancellation and conditional mutation recovery.
- [state/move-destination-state.svelte.ts](./state/move-destination-state.svelte.ts) — Expandable destination folders, independent selection, permission checks and branch-local loading.
- [state/move-destination-state.test.ts](./state/move-destination-state.test.ts) — Selection, expansion, permission boundaries, branch retries and stale-response protection.
- [state/node-update-state.test.ts](./state/node-update-state.test.ts) — Revision reconciliation, picker eligibility, navigation fencing and conflict recovery tests.
- [update-node-api.test.ts](./update-node-api.test.ts) — Atomic PATCH validation, independent permissions, collisions, cycles and retained content tests.

- [state/description-state.svelte.ts](./state/description-state.svelte.ts) — Current-node description eligibility, drafts, conditional saves and explicit conflict recovery.
- [state/description-state.test.ts](./state/description-state.test.ts) — Authoritative reconciliation, creation descriptions, duplicate protection and stale-result tests.
- [description-api.test.ts](./description-api.test.ts) — Conditional description transport, validation, upload metadata and authority tests.
- [browse-api.test.ts](./browse-api.test.ts) — Real state and route request-budget, coherent response validation, denied actions and cancellation tests.
- [state/files-state.svelte.ts](./state/files-state.svelte.ts) — Coherent browsing, capability refresh after moves, access-loss cleanup and concurrent mutation reconciliation.
- [state/personal-root-state.test.ts](./state/personal-root-state.test.ts) — Personal-root navigation, home lookup failures, renamed homes, creation targets and stale responses.
- [api.ts](./api.ts) — Filesystem operations and typed recipient-filtered sharing ports.
- [domain/sharing.ts](./domain/sharing.ts) — Strict group/user grants with required persisted recursive scope, labelled access views and blocked recipients.
- [state/sharing-eligibility-state.svelte.ts](./state/sharing-eligibility-state.svelte.ts) — Browse-seeded sharing eligibility, fresh dialog rechecks and bounded checks for newly created rows.
- [state/sharing-dialog-state.svelte.ts](./state/sharing-dialog-state.svelte.ts) — Recipient drafts, folder contents defaults, legacy scope preservation, widening warnings and conflict recovery.
- [state/recipient-search-state.svelte.ts](./state/recipient-search-state.svelte.ts) — Debounced unified recipient lookup with cancellation, stale-result protection and bounded-result feedback.
- [state/sharing-state.test.ts](./state/sharing-state.test.ts) — Eligibility, mutation, cancellation, self-revocation and stale-result behavior tests.
- [sharing-api.test.ts](./sharing-api.test.ts) — Mixed recipient preservation, scoped query validation and strong conditional JSON transport tests.
- [breadcrumbs-api.test.ts](./breadcrumbs-api.test.ts) — Minimal breadcrumb schemas, visibility boundaries and shared HTTP transport tests.
- [state/navigation-state.svelte.ts](./state/navigation-state.svelte.ts) — Authorized root-to-home paths, confirmed parent links and ancestor overflow.
- [state/navigation-state.test.ts](./state/navigation-state.test.ts) — Deep links, partial paths, stale responses, disposal, ancestor overflow and read isolation tests.
- [domain/](./domain/) — Filesystem validation contracts.
- [errors.ts](./errors.ts) — Safe read, creation and upload failures.
- [state/deletion-state.svelte.ts](./state/deletion-state.svelte.ts) — File eligibility, confirmation, revision capture and safe deletion reconciliation.
- [state/row-deletion-state.svelte.ts](./state/row-deletion-state.svelte.ts) — Browse-seeded row deletion, bounded checks for new rows and cancellation/error/removal focus recovery.
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
