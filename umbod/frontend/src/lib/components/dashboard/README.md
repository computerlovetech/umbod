---
type: Software Module
title: "Dashboard components"
description: "Personal activity dashboard and user connector workspace outside administration."
---

# Files

- [Design preview](./design-preview/README.md) — Sample-data composition of the shared dashboard layouts and charts at /dashboard/preview.

- [CatalogueCapabilities.svelte](./CatalogueCapabilities.svelte) — Read-only capability browsing.
- [CatalogueToolCard.svelte](./CatalogueToolCard.svelte) — Dashboard-owned tool card composition.
- [ConnectorDetail.svelte](./ConnectorDetail.svelte) — User connector detail presentation.
- [ConnectorWorkspace.svelte](./ConnectorWorkspace.svelte) — Combined connector list and selection.
- [Dashboard.svelte](./Dashboard.svelte) — Personal activity dashboard with verified account scoping.
- [ConnectorsPage.svelte](./ConnectorsPage.svelte) — Connector catalogue and personal authorization with authorized connector-query recovery selection and frame-scoped identity.
- [Shared page container](../shared/workspace/PageContainer.svelte) — Common header and content slots shared with Files; catalogue feedback and selection remain feature-owned.
- [Personal activity presentation](../personal/activity/README.md) — Harness and MCP reports with shared period controls and session navigation.
- [Shared dashboard visuals](../shared/dashboard/visualizations/README.md) — Neutral charts shared by live usage and preview; callers own data and eligibility.
- [logout-lifecycle.dom.test.ts](./logout-lifecycle.dom.test.ts) — Pending logout fences refresh events, late profiles and protected page data.
- [connectors-identity.dom.test.ts](./connectors-identity.dom.test.ts) — Recovery deep-link selection, initial identity validation and account epochs fence stale connector data.
- [dashboard-identity.dom.test.ts](./dashboard-identity.dom.test.ts) — Profile and parent account epochs fence stale Dashboard data.
- [dashboard.test.ts](./dashboard.test.ts) — Connector catalogue and workspace presentation tests.
- [dashboard-onboarding.dom.test.ts](./dashboard-onboarding.dom.test.ts) — Loaded Dashboard links to onboarding without duplicating setup instructions.
- [tool-catalogue.test.ts](./tool-catalogue.test.ts) — Tool catalogue presentation tests.
