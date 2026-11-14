---
type: Software Module
title: "Shared namespace management"
description: "Shared namespace administration with revision-safe saves and exact group access."
---

# Files

- [AddNamespaceButton.svelte](./AddNamespaceButton.svelte) — Feature-owned header action opening namespace creation with pending-state protection.

- [NamespaceManagement.svelte](./NamespaceManagement.svelte) — Compact access choices and size-aligned edit actions, with explicit permission saves, guarded reload and separate metadata actions.
- [NamespaceFormModal.svelte](./NamespaceFormModal.svelte) — Feature-local name and optional description dialog, independent of group access assignment.
- [namespace-management-state.svelte.ts](./namespace-management-state.svelte.ts) — Metadata and group access drafts, captured policy revisions, sequential partial-save reconciliation and identity fences.
- [namespace-management-state.test.ts](./namespace-management-state.test.ts) — Draft/save, partial failure, metadata isolation, revision conflicts, reload decisions and obsolete-response tests.
- [namespace-management.dom.test.ts](./namespace-management.dom.test.ts) — Description modal, escaped list text, independent access, dismissal guards and conflict-recovery interactions.
- [NamespaceWorkspaceTestHarness.test-support.svelte](./NamespaceWorkspaceTestHarness.test-support.svelte) — Real group sidebar and namespace editor composition for interaction tests.

- [Group permissions workspace](../group-permissions/README.md) — Persistent shell, catalogue, selection and tab state.
