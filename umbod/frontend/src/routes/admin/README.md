---
type: Software Module
title: Administration routes
description: Capability-checked administration layout, workspaces and compatibility redirects.
---

# Layout

- [Administration authorization](./+layout.ts) — Authenticated profile loading and administration capability checks.
- [Layout tests](./layout.test.ts) — Capability denial, authenticated identity and preserved HTTP failures.
- [Administration entry](./+page.ts) — Redirect to the connector workspace.

# Workspaces

- [Insights and diagnostic patterns](./(agent-insights)/insights/README.md) — Behaviour findings, log analytics and the standalone pattern editor.
- [Portable connector configuration](./(connector-workspace)/portable-connectors/+page.svelte) — Deep links to configure submitted portable connectors in the shared inventory.
- [Groups](./groups/README.md) — Central administrator group catalogue route.
- [Shared namespaces](./namespaces/+page.svelte) — Administration inventory for creating, editing, and deleting shared namespaces.
- [Agent tokens](./agent-tokens/+page.svelte) — Administrator inventory for issuing, rotating, and revoking public MCP agent tokens.
- [Permissions](./group-permissions/README.md) — Persistent permissions layout and lazy tab editors.
- [System settings](./system-settings/+page.svelte) — Instance-wide filesystem approval and diagnostic reporting settings.

# Compatibility redirects

- [Agent behaviour](./agent-behaviour/README.md) — Legacy route redirecting to Insights findings.
- [Log analytics](./analytics/README.md) — Legacy route redirecting to Insights log analytics.
