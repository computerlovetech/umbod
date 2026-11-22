---
type: Software Module
title: Insights composition
description: Identity-scoped navigation and state shared by Insights and the standalone Agent diagnostics editor.
---

# Files

- [InsightsLayout.svelte](./InsightsLayout.svelte) — Identity-keyed state boundary and administrator navigation selection.
- [InsightsWorkspace.svelte](./InsightsWorkspace.svelte) — Shared access handling; renders Insights tabs only for findings and logs.
- [insights-state.svelte.ts](./insights-state.svelte.ts) — Persistent configuration ownership and cross-feature access-loss disposal.
- [insights-context.ts](./insights-context.ts) — Typed subtree-scoped access to the Insights owner.
- [insights-factory.ts](./insights-factory.ts) — Explicit composition of feature API adapters and scoped state.
- [insights-navigation.ts](./insights-navigation.ts) — URL-derived Insights tab selection and standalone diagnostics route detection.
- [insights-layout.dom.test.ts](./insights-layout.dom.test.ts) — Route composition, draft persistence, identity changes and authorization-loss interactions.
- [insights-state.test.ts](./insights-state.test.ts) — Cross-feature cancellation and obsolete-response fences.
- [InsightsHarness.test-support.svelte](./InsightsHarness.test-support.svelte) — Routed component harness for scoped ownership tests.
- [insights.test-support.svelte.ts](./insights.test-support.svelte.ts) — Typed configuration fixture and reactive test-router inputs.
- [Shared presentation](../../shared/workspace/README.md) — Neutral page frame, route navigation and query disclosure controls.
