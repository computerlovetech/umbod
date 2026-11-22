---
type: Software Module
title: Insights and Agent diagnostics routes
description: Administration routes for behaviour findings, log analytics and the standalone diagnostics editor.
---

# Files

- [Shared layout](../+layout.svelte) — Keeps identity-scoped state across Insights and Agent diagnostics beneath the administration guard.
- [Landing redirect](./+page.ts) — Default destination for the Insights section.
- [Agent behaviour](./agent-behaviour/+page.svelte) — Findings landing view with feature-owned default query loading.
- [Agent diagnostics](../agent-diagnostics/+page.svelte) — Standalone pattern editor using the persistent configuration draft.
- [Legacy configuration redirect](./agent-behaviour/configuration/+page.ts) — Preserves the query and fragment when redirecting to Agent diagnostics.
- [Log analytics](./logs/+page.svelte) — View-scoped analytics queries and results.
- [navigation.test.ts](./navigation.test.ts) — Landing and legacy redirects with preserved query and fragment.
- [Insights composition](../../../../lib/components/admin/insights/README.md) — Section navigation, shared state ownership and access-loss handling.
- [Administration authorization](../../+layout.ts) — Existing profile and administration capability validation.
