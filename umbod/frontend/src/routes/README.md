---
type: Software Module
title: "Routes"
description: "Static SvelteKit SPA layouts, browser loaders and page composition."
---

# Files

- [+error.svelte](./+error.svelte) — Access and load failure presentation.
- [+layout.svelte](./+layout.svelte) — Application layout.
- [+layout.ts](./+layout.ts) — SPA configuration loader.
- [+page.ts](./+page.ts) — Dashboard entry redirect.
- [admin/](./admin/README.md) — Capability-checked administration layout, workspaces and compatibility redirects.
- [Workspace routes](./(workspace)/README.md) — Persistent user sidebar, access lifetime and child pages without URL prefixes.
- [Dashboard preview](./dashboard/preview/+page.svelte) — Standalone sample-data frame outside the authenticated workspace group.
- [error.test.ts](./error.test.ts) — Route error presentation tests.
- [navigation.test.ts](./navigation.test.ts) — Route navigation tests.

# Context not available from the code

- [ADR-004: One Backend API and a Thin Desktop Boundary](../../../project/architecture-records/ADR-004-single-backend-api-and-desktop-boundary.md) — Backend API ownership.
