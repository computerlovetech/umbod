---
type: Software Module
title: "Group permissions components"
description: "Persistent group permissions workspace, tab editors and permission drafts."
---

# Files

- [group-permissions-components.test.ts](./group-permissions-components.test.ts) — Permission workspace presentation tests.
- [group-permissions-catalogue.dom.test.ts](./group-permissions-catalogue.dom.test.ts) — Mounted catalogue updates and named unavailable-grant removal, save and failure interactions.
- [group-permissions-loader.ts](./group-permissions-loader.ts) — Selected group reads, assignable targets and display-only connector inventory.
- [group-permissions-state.svelte.ts](./group-permissions-state.svelte.ts) — Connector grant drafts, eligibility and named unavailable-grant projections.
- [group-permissions-state.test.ts](./group-permissions-state.test.ts) — Group selection, exact grant eligibility, metadata fallback and disposal fencing tests.
- [GroupPermissionsManager.svelte](./GroupPermissionsManager.svelte) — Connector permission detail and state-owned save controls.
- [GroupPermissionsWorkspace.svelte](./GroupPermissionsWorkspace.svelte) — Persistent group sidebar, selected-group header and editor slot.
- [group-permissions-context.ts](./group-permissions-context.ts) — Layout-scoped workspace context.
- [group-permissions-route-state.svelte.ts](./group-permissions-route-state.svelte.ts) — URL-derived tabs, descriptions and validated deep links.
- [group-permissions-workspace-state.svelte.ts](./group-permissions-workspace-state.svelte.ts) — Layout-owned namespace and connector states, lazy loading, shared selection and cross-tab discard guards.
- [group-permissions-workspace-state.test.ts](./group-permissions-workspace-state.test.ts) — Lazy loading, draft retention, shared selection and disposal tests.
- [group-permissions-workspace.dom.test.ts](./group-permissions-workspace.dom.test.ts) — Stable chrome, editor replacement and save-after-unmount tests.
- [group-permissions-saver.ts](./group-permissions-saver.ts) — Connector save port and validated browser adapter.
- [group-permissions-save.test.ts](./group-permissions-save.test.ts) — State-owned save reconciliation and failure tests.
- [workspace.test-support.ts](./workspace.test-support.ts) — In-memory workspace dependencies and request tracking.
- [WorkspaceTestHarness.test-support.svelte](./WorkspaceTestHarness.test-support.svelte) — Mounted tab-editor composition for lifecycle tests.
- [GroupPermissionsPage.svelte](./GroupPermissionsPage.svelte) — Shared page heading, tabs and editor spacing.
- [GroupPermissionsGroupHeader.svelte](./GroupPermissionsGroupHeader.svelte) — Shared selected-group identity and optional badge.
- [group-permissions-layout.test.ts](./group-permissions-layout.test.ts) — Shared page composition and group identity presentation tests.
- [GroupPermissionsGroupList.svelte](./GroupPermissionsGroupList.svelte) — Connector catalogue group selection, styling and accessibility.
- [group-permissions-group-list.dom.test.ts](./group-permissions-group-list.dom.test.ts) — Group selection callbacks and reactive presentation tests.
- [GroupPermissionsTabs.svelte](./GroupPermissionsTabs.svelte) — Connector and filesystem routes composed through shared subpage navigation.
- [shared/](./shared/) — Native dialog compatibility export.
- [Group management](../groups/README.md) — Central catalogue labels, descriptions and registration.
