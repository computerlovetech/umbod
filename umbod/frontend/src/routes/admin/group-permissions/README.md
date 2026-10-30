---
type: Software Module
title: Group permissions routes
description: Persistent administration shell, shared catalogue and independent permission editors.
---

# Files

- [+layout.ts](./+layout.ts) — Shared catalogue loading and access error propagation.
- [+layout.svelte](./+layout.svelte) — Section-scoped workspace composition, activation and disposal.
- [+page.ts](./+page.ts) — Default connector-tab redirect preserving query and fragment.
- [connectors/+page.ts](./connectors/+page.ts) — Validated deep-link parsing without permission refetches.
- [connectors/+page.svelte](./connectors/+page.svelte) — Connector detail consuming retained workspace state.
- [filesystem/+page.svelte](./filesystem/+page.svelte) — Filesystem detail consuming retained workspace state.
- [navigation.test.ts](./navigation.test.ts) — Parent loading, deep-link validation and redirect tests.
- [pages.test.ts](./pages.test.ts) — Shared layout presentation and navigation tests.
- [Permissions components](../../../lib/components/admin/group-permissions/README.md) — Shared workspace and editor state.
