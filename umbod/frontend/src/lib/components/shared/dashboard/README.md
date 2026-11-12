---
type: Software Module
title: Dashboard presentation
description: Data-independent dashboard layout primitives for composing visual panels in responsive rows and columns.
---

# Layout

- [DashboardContainer.svelte](./DashboardContainer.svelte) — Named dashboard section with a heading, caller-owned toolbar, rows and optional footer.
- [DashboardRow.svelte](./DashboardRow.svelte) — Twelve-track row for dashboard columns; keeps sibling panels aligned without fixing viewport height.
- [DashboardColumn.svelte](./DashboardColumn.svelte) — Explicit one-to-twelve column span; stacks below a 760px dashboard container width.
- [DashboardPanel.svelte](./DashboardPanel.svelte) — Named visual surface with a level-three heading, metadata, optional actions and caller-owned visualization.

- [DashboardPeriodSwitch.svelte](./DashboardPeriodSwitch.svelte) — Controlled 7/30-day buttons shared by the live and preview toolbars.

# Visual components

- [Visualizations](./visualizations/README.md) — Neutral outcome, operation-mix, daily-activity and tool-ranking presenters shared by live and preview dashboards.

# Verification

- [period-switch.dom.test.ts](./period-switch.dom.test.ts) — Pressed-state buttons, typed selection callbacks and parent-controlled selection updates.
- [layout.dom.test.ts](./layout.dom.test.ts) — Panel composition, accessible headings and caller-owned toolbar, panel actions and footer.
- [layout.test-support.svelte](./layout.test-support.svelte) — Mounted multi-row composition fixture for layout tests.
