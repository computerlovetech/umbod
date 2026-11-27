---
type: Software Module
title: Workspace routes
description: Persistent user workspace layout and child routes with unchanged public URLs.
---

# Files

- [+layout.svelte](./+layout.svelte) — Persistent frame receiving root identity data and current pathname.
- [Workspace frame](../../lib/components/workspace/README.md) — Feature-owned shell, access scope and lifecycle regression tests.
- [Dashboard](./dashboard/+page.svelte) — Personal harness and Umbod MCP activity at /dashboard.
- [Connectors](./connectors/+page.svelte) — Connector catalogue and personal authorization content at /connectors.
- [Files](./files/+page.svelte) — Filesystem content at /files.
- [Insights](./insights/+layout.svelte) — Personal diagnostic reports and advanced log analytics.
- [Legacy activity redirect](./insights/activity/+page.ts) — Routes existing Insights activity bookmarks to Dashboard.
- [Getting started](./getting-started/README.md) — Harness onboarding under the retained workspace frame.
- [Account settings](./settings/README.md) — Read-only profile and personal access token management.
