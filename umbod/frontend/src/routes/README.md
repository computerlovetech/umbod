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
- [admin/](./admin/) — Administration routes and capability-checked profile layout; the root redirects to Connectors.
- [Admin layout tests](./admin/layout.test.ts) — Explicit capability denial, authenticated identity and preserved HTTP failures.
- [Insights](./admin/insights/README.md) — Separate behaviour findings, configuration and log analytics with identity-scoped ownership.
- [Groups](./admin/groups/README.md) — Central administrator group catalogue route.
- [Group permissions](./admin/group-permissions/README.md) — Persistent permissions layout and lazy tab editors.
- [Workspace routes](./(workspace)/README.md) — Persistent user sidebar, access lifetime and child pages without URL prefixes.
- [Dashboard preview](./dashboard/preview/+page.svelte) — Standalone sample-data frame outside the authenticated workspace group.
- [error.test.ts](./error.test.ts) — Route error presentation tests.
- [navigation.test.ts](./navigation.test.ts) — Route navigation tests.

# Context not available from the code

- [ADR-004: One Backend API and a Thin Desktop Boundary](../../../project/architecture-records/ADR-004-single-backend-api-and-desktop-boundary.md) — Backend API ownership.
