---
type: Software Module
title: Group management
description: Central administration catalogue metadata forms and operation state.
---

# Files

- [GroupsManager.svelte](./GroupsManager.svelte) — Accessible catalogue, modal entry points and deletion confirmation.
- [GroupFormModal.svelte](./GroupFormModal.svelte) — Group creation and editing with visible login-observed suggestions and manual provider-ID entry.
- [GroupsWorkspace.svelte](./GroupsWorkspace.svelte) — Catalogue state ownership and disposal at the route data boundary.
- [groups-state.svelte.ts](./groups-state.svelte.ts) — In-place metadata reconciliation and revision recovery.
- [group-suggestions.svelte.ts](./group-suggestions.svelte.ts) — Independent lazy provider-value search and obsolete-response fencing.
- [group-suggestions.test.ts](./group-suggestions.test.ts) — Draft isolation, stale results and manual fallback checks.
- [groups-state.test.ts](./groups-state.test.ts) — Operation state, identity and authorization tests.
- [groups-components.dom.test.ts](./groups-components.dom.test.ts) — Mounted form wiring and disposal tests.
