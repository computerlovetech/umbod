---
type: Software Module
title: Dashboard visualizations
description: Neutral dashboard chart and ranking presentation for caller-prepared render data.
---

# Files

- [OutcomeRing.svelte](./OutcomeRing.svelte) — Labelled success, failure and cancellation ring; zero calls retain the neutral ring and legend without values or explanatory text.
- [OperationMixChart.svelte](./OperationMixChart.svelte) — Proportional category strip with counts and shares; callers prepare totals and percentages.
- [DailyActivityChart.svelte](./DailyActivityChart.svelte) — Stacked tool activity with per-day outcome labels; callers supply a positive axis maximum.
- [ToolRankingList.svelte](./ToolRankingList.svelte) — Ranked tool identities, connectors, counts and bars; empty inputs show five static decorative ranking silhouettes.
- [EmptyToolRanking.svelte](./EmptyToolRanking.svelte) — Internal empty-ranking presenter with five decorative rows, no fabricated usage or loading animation.
- [types.ts](./types.ts) — Read-only presentational contracts without feature controllers, API schemas or authentication policy.
- [visualizations.css](./visualizations.css) — Shared visual mechanics and overridable semantic outcome and category colour tokens.
- [visualizations.dom.test.ts](./visualizations.dom.test.ts) — Labels, prop updates, zero states and ranked identities through mounted neutral components.
- [visualization-props.test-support.svelte.ts](./visualization-props.test-support.svelte.ts) — Reactive test input replacement for visualization prop-update coverage.
