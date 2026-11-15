---
type: Software Module
title: Workspace frame
description: Feature-owned persistent user sidebar and explicitly scoped access lifecycle.
---

# Files

- [WorkspaceFrame.svelte](./WorkspaceFrame.svelte) — Owns one profile access state, shell and disposal scope across workspace child routes.
- [Workspace state](../../workspace/README.md) — Typed scoped context, identity source fences and pathname-derived active navigation.
- [workspace-lifecycle.dom.test.ts](./workspace-lifecycle.dom.test.ts) — Real root and group layouts retain account DOM, avoid repeated profile reads and fence group reentry.
- [WorkspaceRootHarness.test-support.svelte](./WorkspaceRootHarness.test-support.svelte) — Root-boundary composition with persistent group layout and replaceable child content.
- [workspace-route.test-support.svelte.ts](./workspace-route.test-support.svelte.ts) — Reactive route inputs for child changes and group exit.
- [WorkspacePageHarness.test-support.svelte](./WorkspacePageHarness.test-support.svelte) — Real frame and typed child composition for existing identity and rendering regressions.
- [mount-workspace.test-support.ts](./mount-workspace.test-support.ts) — Mount page content within its real access and shell scope.
- [render-workspace.test-support.ts](./render-workspace.test-support.ts) — Server-render page content within the real frame without profile I/O.
