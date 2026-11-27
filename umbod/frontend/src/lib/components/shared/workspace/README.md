---
type: Software Module
title: Workspace presentation
description: Shared application shell and actor-independent subpage presentation.
---

# Files

- [WorkspaceShell.svelte](./WorkspaceShell.svelte) — Expandable desktop icon rail, optional return link, mobile drawer, and account menu.
- [mobile-navigation.ts](./mobile-navigation.ts) — Responsive popover lifecycle and link dismissal shared by sidebar drawers.
- [Mobile navigation styles](../../../styles/mobile-navigation.css) — Shared mobile drawer layout, controls and backdrop.
- [WorkspaceNavigationIcon.svelte](./WorkspaceNavigationIcon.svelte) — Internal decorative outline icons for workspace and administration navigation links.
- [workspace-sidebar.dom.test.ts](./workspace-sidebar.dom.test.ts) — Shared rail preference, icon accessibility, remembered return links and sidebar motion rendering.
- [workspace-shell-state.svelte.ts](./workspace-shell-state.svelte.ts) — Workspace navigation and account presentation state.
- [workspace-shell.test.ts](./workspace-shell.test.ts) — Workspace shell, navigation and account rendering tests.
- [PageContainer.svelte](./PageContainer.svelte) — Neutral heading, optional actions and content slots shared by Files and Connectors; callers own state and feature markup.
- [page-container.dom.test.ts](./page-container.dom.test.ts) — Injected slot placement, omitted actions and retained DOM, input drafts and focus during updates.
- [Page container fixture](./page-container.test-support.svelte) — Test-only injected heading, optional actions, sidebar and detail content.
- [SubpageContainer.svelte](./SubpageContainer.svelte) — Page heading, optional action slot, navigation slot and selected content.
- [SubpageNavigation.svelte](./SubpageNavigation.svelte) — Controlled horizontal route links, current page or parent location, and pending feedback.
- [QueryPanel.svelte](./QueryPanel.svelte) — Shared query disclosure with caller-owned parameters, reset and submission.
- [query-panel.dom.test.ts](./query-panel.dom.test.ts) — Pending protection, draft reset, successful collapse and focus restoration.
- [Subpage navigation styles](../../../styles/subpage-navigation.css) — Shared underline, hover and keyboard-focus presentation for route links and in-place tabs.
- [subpage-container.test.ts](./subpage-container.test.ts) — Neutral heading, action, navigation and current-page rendering tests.
