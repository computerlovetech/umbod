---
type: Software Module
title: Log analytics presentation
description: Feature-owned administrator query form and authoritative log-count table.
---

# Files

- [Workspace](AnalyticsWorkspace.svelte) — Compact query toolbar, observed-value filter picker and server-paged results with page totals.
- [DOM tests](analytics-workspace.dom.test.ts) — Filter selection, grouping, server page navigation, submit, retry and access-loss interactions.
- [State and contracts](../../../admin/analytics/README.md) — Feature state and validated I/O boundary.
- [Page](../../../../routes/admin/analytics/+page.svelte) — Thin administrator route composition.
