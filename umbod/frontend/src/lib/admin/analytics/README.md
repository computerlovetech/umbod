---
type: Software Module
title: Log analytics
description: Administrator log-count query contracts, request adapter and explicit query state.
---

# Files

- [Schemas](domain/schemas.ts) — Validated query and result contracts.
- [Port](port.ts) — Log-count query boundary.
- [HTTP adapter](http-route.ts) — Administrator telemetry route over the shared transport.
- [Query draft](query-draft.svelte.ts) — Exact filters, ordered grouping and explicit-offset range conversion.
- [Query state](analytics-state.svelte.ts) — Submitted results, pending work, retry and access-loss fencing.
- [In-memory adapter](in-memory.test-support.ts) — Test-only validated response and request control.
- [State tests](analytics-state.test.ts) — Draft preservation, time conversion, limits and asynchronous lifetimes.
- [Route tests](http-route.test.ts) — Outbound and inbound validation through the composite API.
- [Presentation](../../components/admin/analytics/README.md) — Feature-owned query form and results table.
