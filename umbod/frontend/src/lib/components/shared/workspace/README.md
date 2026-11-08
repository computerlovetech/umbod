---
type: Software Module
title: Workspace presentation
description: Shared application shell and actor-independent subpage presentation.
---

# Files

- [WorkspaceShell.svelte](./WorkspaceShell.svelte) — Contextual sidebar, optional section heading and return link, account identity and logout frame.
- [WorkspaceNavigationIcon.svelte](./WorkspaceNavigationIcon.svelte) — Internal decorative outline icons for workspace and administration navigation links.
- [workspace-sidebar.dom.test.ts](./workspace-sidebar.dom.test.ts) — Context isolation, icon accessibility, remembered return links and sidebar motion rendering.
- [workspace-shell-state.svelte.ts](./workspace-shell-state.svelte.ts) — Workspace navigation and account presentation state.
- [workspace-shell.test.ts](./workspace-shell.test.ts) — Workspace shell, navigation and account rendering tests.
- [SubpageContainer.svelte](./SubpageContainer.svelte) — Page heading, optional action slot, navigation slot and selected content.
- [SubpageNavigation.svelte](./SubpageNavigation.svelte) — Controlled horizontal route links and pending navigation feedback.
- [subpage-container.test.ts](./subpage-container.test.ts) — Neutral heading, action, navigation and current-page rendering tests.
