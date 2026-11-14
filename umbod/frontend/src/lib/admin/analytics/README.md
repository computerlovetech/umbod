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
- [Reports](reports.ts) — Session activity and Stored logs presets, grouping and count labels.
- [Report tests](reports.test.ts) — Primary-only requests, all-session reports, frozen session drill-down, retry and independent drafts.
- [Query state](analytics-state.svelte.ts) — One-shot default loading, applied summaries, draft reset, session narrowing and access-loss notification.
- [Filter choices](filter-choices.svelte.ts) — Paginated observed-value discovery, manual custom session filters, range freshness and cancellation.
- [Filter choice tests](filter-choices.svelte.test.ts) — Discovery, manual session entry, selection guards, failures and obsolete-response fencing.
- [In-memory adapter](in-memory.test-support.ts) — Test-only validated response and request control.
- [State tests](analytics-state.test.ts) — Default loading, boolean submission results, applied summaries, draft reset, pagination and asynchronous lifetimes.
- [Route tests](http-route.test.ts) — Outbound and inbound validation through the composite API.
- [Presentation](../../components/admin/analytics/README.md) — Feature-owned query form and results table.
