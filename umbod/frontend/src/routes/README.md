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
- [admin/](./admin/) — Administration routes and access layout.
- [dashboard/](./dashboard/) — User catalogue page.
- [error.test.ts](./error.test.ts) — Route error presentation tests.
- [files/](./files/) — User filesystem page.
- [navigation.test.ts](./navigation.test.ts) — Route navigation tests.

# Context not available from the code

- [ADR-004: One Backend API and a Thin Desktop Boundary](../../../project/architecture-records/ADR-004-single-backend-api-and-desktop-boundary.md) — Backend API ownership.
