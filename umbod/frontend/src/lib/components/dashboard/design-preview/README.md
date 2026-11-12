---
type: Software Module
title: Dashboard design preview
description: Sample-data dashboard composition sharing neutral layouts and visualizations with live usage.
---

# Files

- [Shared visualizations](../../shared/dashboard/visualizations/README.md) — Neutral rendering contracts used by preview and live usage.

- [DashboardPreview.svelte](./DashboardPreview.svelte) — Sample/empty comparison with shared charts, period buttons and sample-only connector filters at /dashboard/preview.
- [preview-state.svelte.ts](./preview-state.svelte.ts) — Sample/empty scenarios and period-dependent projections; preserves filters across comparisons without account data or network access.
- [preview-ranking.dom.test.ts](./preview-ranking.dom.test.ts) — Scenario comparison, decorative empty shapes, period/filter preservation and empty-selection recovery through controls.
- [preview-state.test.ts](./preview-state.test.ts) — Outcome ratios, top-five ordering, connector filtering, empty selection and period changes.
