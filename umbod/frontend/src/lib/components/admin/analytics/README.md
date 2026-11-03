---
type: Software Module
title: Log analytics presentation
description: Feature-owned administrator query form and authoritative log-count table.
---

# Files

- [Workspace](AnalyticsWorkspace.svelte) — Compact query toolbar, observed-value filter picker, advanced settings and tabular results.
- [DOM tests](analytics-workspace.dom.test.ts) — Filter search and keyboard selection, grouping, submit, retry and access-loss interactions.
- [State and contracts](../../../admin/analytics/README.md) — Feature state and validated I/O boundary.
- [Page](../../../../routes/admin/analytics/+page.svelte) — Thin administrator route composition.
