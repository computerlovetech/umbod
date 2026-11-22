---
type: Software Module
title: Log analytics presentation
description: Feature-owned administrator query form and authoritative log-count table.
---

# Files

- [Workspace](AnalyticsWorkspace.svelte) — Auto-loaded logs, collapsed query editor, compact results and an independent custom explorer.
- [DOM tests](analytics-workspace.dom.test.ts) — Default query, results without auxiliary details or requests, editor folding, frozen navigation, filters and access loss.
- [State and contracts](../../../admin/analytics/README.md) — Feature state and validated I/O boundary.
- [Insights workspace](../insights/InsightsWorkspace.svelte) — Provides access handling and navigation between behaviour findings and log analytics.
