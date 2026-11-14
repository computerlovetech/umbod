---
type: Software Module
title: Insights composition
description: Identity-scoped navigation and feature lifetimes for administration insights.
---

# Files

- [InsightsLayout.svelte](./InsightsLayout.svelte) — Administration shell and identity-keyed ownership boundary.
- [InsightsWorkspace.svelte](./InsightsWorkspace.svelte) — Shared Insights heading, contextual actions, route navigation and feature content.
- [insights-state.svelte.ts](./insights-state.svelte.ts) — Persistent configuration ownership and cross-feature access-loss disposal.
- [insights-context.ts](./insights-context.ts) — Typed subtree-scoped access to the Insights owner.
- [insights-factory.ts](./insights-factory.ts) — Explicit composition of feature API adapters and scoped state.
- [insights-navigation.ts](./insights-navigation.ts) — URL-derived view selection and parent location for Configuration.
- [insights-layout.dom.test.ts](./insights-layout.dom.test.ts) — Route composition, draft persistence, identity changes and authorization-loss interactions.
- [insights-state.test.ts](./insights-state.test.ts) — Cross-feature cancellation and obsolete-response fences.
- [InsightsHarness.test-support.svelte](./InsightsHarness.test-support.svelte) — Routed component harness for scoped ownership tests.
- [insights.test-support.svelte.ts](./insights.test-support.svelte.ts) — Typed configuration fixture and reactive test-router inputs.
- [Shared presentation](../../shared/workspace/README.md) — Neutral page frame, route navigation and query disclosure controls.
