---
type: Software Module
title: "Frontend components"
description: "Reusable and actor-owned Svelte presentation and interaction modules."
---

# Files

- [admin/](./admin/) — Administration views and controls.
- [Insights](./admin/insights/README.md) — Identity-scoped administration insights navigation and feature lifetimes.
- [Log analytics](./admin/analytics/README.md) — Feature-owned administrator query form and results table.
- [Connector list empty state](./admin/connectors/ConnectorListEmptyState.svelte) — Consistent empty-list presentation for catalog, OpenAPI, and MCP tabs.
- [Agent behaviour](./admin/agent-behaviour/README.md) — Definition forms and self-reported diagnostic report inspection.
- [Group management](./admin/groups/README.md) — Central administrator group catalogue forms.
- [Workspace frame](./workspace/README.md) — Route-group-owned sidebar, profile access and scoped page lifetimes.
- [dashboard](./dashboard/README.md) — User catalogue workspace.
- [feedback/](./feedback/) — Toast presentation and state.
- [files](./files/README.md) — User filesystem workspace.
- [Getting started](./getting-started/README.md) — Unified harness connections and personal telemetry onboarding.
- [Identity observation](./identity-directory/README.md) — Root-mounted browser observation lifecycle.
- [header/](./header/) — Header and account presentation.
- [personal-connections](./personal-connections/README.md) — Owner-scoped connection controls.
- [Personal MCP administration](./admin/personal-mcp-servers/README.md) — Actor-owned policy editing and pre-publication OAuth setup.
- [shared](./shared/README.md) — Actor-independent presentation.

# Context not available from the code

- [ADR-007: Actor-Specific Composition](../../../../project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Shared mechanics and actor-owned presentation boundaries.
- [Semantic theme](../styles/admin.css) — Palette derived from the website and documentation; retain intentional vendor logo colours.
