---
type: Software Module
title: Insights routes
description: Separate behaviour findings, configuration and log analytics under one administration section.
---

# Files

- [Layout](./+layout.svelte) — Persistent identity-scoped Insights composition beneath the existing administration guard.
- [Landing redirect](./+page.ts) — Default destination for the Insights section.
- [Agent behaviour](./agent-behaviour/+page.svelte) — Findings landing view with feature-owned default query loading.
- [Configuration](./agent-behaviour/configuration/+page.svelte) — Pattern setup using the persistent configuration draft.
- [Log analytics](./logs/+page.svelte) — View-scoped analytics queries and results.
- [navigation.test.ts](./navigation.test.ts) — Landing and legacy redirects with preserved query and fragment.
- [Insights composition](../../../lib/components/admin/insights/README.md) — Navigation, contextual actions, ownership and access-loss fences.
- [Administration authorization](../+layout.ts) — Existing profile and administration capability validation.
