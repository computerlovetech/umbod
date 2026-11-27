---
type: Software Module
title: "Frontend components"
description: "Reusable and actor-owned Svelte presentation and interaction modules."
---

# Files

- [admin/](./admin/README.md) — Administration workspaces, permissions and shared controls.
- [Workspace frame](./workspace/README.md) — Route-group-owned sidebar, profile access and scoped page lifetimes.
- [Dashboard and Connectors](./dashboard/README.md) — Account-scoped Dashboard composition, catalogue workspace, and standalone design preview.
- [feedback/](./feedback/) — Toast presentation and state.
- [files](./files/README.md) — User filesystem workspace.
- [Getting started](./getting-started/README.md) — Harness installation and connection guidance.
- [Settings](./settings/README.md) — Personal token management and one-time telemetry configuration.
- [Identity observation](./identity-directory/README.md) — Root-mounted browser observation lifecycle.
- [header/](./header/) — Header and account presentation.
- [Personal activity](./personal/activity/README.md) — Harness and MCP reports with personal session navigation.
- [personal-connections](./personal-connections/README.md) — Owner-scoped connection controls.
- [shared](./shared/README.md) — Actor-independent presentation.

# Context not available from the code

- [ADR-007: Actor-Specific Composition](../../../../project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Shared mechanics and actor-owned presentation boundaries.
- [Semantic theme](../styles/admin.css) — Palette derived from the website and documentation; retain intentional vendor logo colours.
