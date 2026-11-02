---
type: Software Module
title: Log analytics presentation
description: Feature-owned administrator query form and authoritative log-count table.
---

# Files

- [Workspace](AnalyticsWorkspace.svelte) — Accessible query controls, submitted context, count summaries and tabular results.
- [DOM tests](analytics-workspace.dom.test.ts) — Actual filter, grouping, submit, retry and access-loss interactions.
- [State and contracts](../../../admin/analytics/README.md) — Feature state and validated I/O boundary.
- [Page](../../../../routes/admin/analytics/+page.svelte) — Thin administrator route composition.
