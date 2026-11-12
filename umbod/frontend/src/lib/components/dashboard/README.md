---
type: Software Module
title: "Dashboard components"
description: "Separate personal usage and user connector workspace compositions outside administration."
---

# Files

- [Design preview](./design-preview/README.md) — Sample-data composition of the shared dashboard layouts and charts at /dashboard/preview.

- [CatalogueCapabilities.svelte](./CatalogueCapabilities.svelte) — Read-only capability browsing.
- [CatalogueToolCard.svelte](./CatalogueToolCard.svelte) — Dashboard-owned tool card composition.
- [ConnectorDetail.svelte](./ConnectorDetail.svelte) — User connector detail presentation.
- [ConnectorWorkspace.svelte](./ConnectorWorkspace.svelte) — Combined connector list and selection.
- [Dashboard.svelte](./Dashboard.svelte) — Usage-only page with independent profile access and account fencing.
- [ConnectorsPage.svelte](./ConnectorsPage.svelte) — Connector catalogue and personal authorization page with independent profile access.
- [PersonalUsage.svelte](./PersonalUsage.svelte) — Feature-owned usage charts, shared period buttons and status controls; empty panels stay visible without explanatory text.
- [Shared dashboard visuals](../shared/dashboard/visualizations/README.md) — Neutral charts shared by live usage and preview; callers own data and eligibility.
- [personal-usage.dom.test.ts](./personal-usage.dom.test.ts) — Usage interactions and independent loading.
- [logout-lifecycle.dom.test.ts](./logout-lifecycle.dom.test.ts) — Pending logout fences refresh events, late profiles and protected page data.
- [connectors-identity.dom.test.ts](./connectors-identity.dom.test.ts) — Profile and parent account epochs fence stale connector data.
- [dashboard-identity.dom.test.ts](./dashboard-identity.dom.test.ts) — Profile and parent account epochs fence stale Dashboard data.
- [dashboard.test.ts](./dashboard.test.ts) — Connector catalogue and workspace presentation tests.
- [dashboard-onboarding.dom.test.ts](./dashboard-onboarding.dom.test.ts) — Loaded Dashboard links to onboarding without duplicating setup instructions.
- [tool-catalogue.test.ts](./tool-catalogue.test.ts) — Tool catalogue presentation tests.
