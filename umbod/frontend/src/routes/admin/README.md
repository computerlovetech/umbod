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

- [Insights and Agent diagnostics](./(agent-insights)/insights/README.md) — Behaviour findings, log analytics and the standalone diagnostics editor.
- [Groups](./groups/README.md) — Central administrator group catalogue route.
- [Shared namespaces](./namespaces/+page.svelte) — Administration inventory for creating, editing, and deleting shared namespaces.
- [Permissions](./group-permissions/README.md) — Persistent permissions layout and lazy tab editors.

# Compatibility redirects

- [Agent behaviour](./agent-behaviour/README.md) — Legacy route redirecting to Insights findings.
- [Log analytics](./analytics/README.md) — Legacy route redirecting to Insights log analytics.
