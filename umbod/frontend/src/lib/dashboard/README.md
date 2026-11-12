---
type: Software Module
title: "Dashboard"
description: "Independent personal usage and connector catalogue contracts and page lifetimes."
---

# Files

- [chart-projections.ts](./chart-projections.ts) — Tool-only outcomes and daily activity, all-category operation shares and finite empty chart data.
- [chart-projections.test.ts](./chart-projections.test.ts) — Category separation, cancellation denominators, zero snapshots and varied periods.
- [api.ts](./api.ts) — Independent catalogue and personal usage ports.
- [domain/](./domain/) — Catalogue validation; tool schema changes require coordinated backend/frontend deployment.
- [infrastructure/](./infrastructure/) — Catalogue HTTP and in-memory adapters.
- [presentation.ts](./presentation.ts) — Connector labels and sidebar identities.
- [state/](./state/) — Separate usage and connector lifetimes with capability search.
- [domain/usage-schemas.ts](./domain/usage-schemas.ts) — Validated personal UTC usage snapshots.
- [infrastructure/usage-route.ts](./infrastructure/usage-route.ts) — Authenticated personal usage route.
- [state/usage-state.svelte.ts](./state/usage-state.svelte.ts) — Independent usage loading, periods and identity fences.
- [state/usage-page-state.svelte.ts](./state/usage-page-state.svelte.ts) — Account observation and usage-only page lifecycle.
- [test-fixtures.ts](./test-fixtures.ts) — Catalogue test fixtures.
