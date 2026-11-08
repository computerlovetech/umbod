---
type: Software Module
title: Log analytics presentation
description: Feature-owned administrator query form and authoritative log-count table.
---

# Files

- [Workspace](AnalyticsWorkspace.svelte) — All-session reports with result-driven session drill-down and a secondary server-paged custom explorer.
- [DOM tests](analytics-workspace.dom.test.ts) — All-session reports, clickable sessions, custom session entry, canonical labels, frozen pages, retry and access loss.
- [State and contracts](../../../admin/analytics/README.md) — Feature state and validated I/O boundary.
- [Page](../../../../routes/admin/analytics/+page.svelte) — Thin administrator route composition.
