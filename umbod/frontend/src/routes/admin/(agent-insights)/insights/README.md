---
type: Software Module
title: Insights routes
description: Administration routes for behaviour findings, log analytics and standalone diagnostic patterns.
---

# Files

- [Shared layout](../+layout.svelte) — Keeps identity-scoped state across Insights and standalone patterns beneath the administration guard.
- [Landing redirect](./+page.ts) — Default destination for the Insights section.
- [Agent behaviour](./agent-behaviour/+page.svelte) — Findings landing view with feature-owned default query loading.
- [Agent diagnostics](../agent-diagnostics/+page.svelte) — Standalone pattern editor with links to findings and reporting settings.
- [Legacy reporting redirect](../agent-diagnostics/+page.ts) — Sends legacy reporting tab URLs to System settings.
- [Legacy configuration redirect](./agent-behaviour/configuration/+page.ts) — Routes older settings URLs to standalone patterns or reporting settings while preserving the fragment.
- [Log analytics](./logs/+page.svelte) — View-scoped analytics queries and results.
- [navigation.test.ts](./navigation.test.ts) — Standalone patterns routing and legacy redirects with preserved query and fragment.
- [Insights composition](../../../../lib/components/admin/insights/README.md) — Section navigation, shared state ownership and access-loss handling.
- [Administration authorization](../../+layout.ts) — Existing profile and administration capability validation.
