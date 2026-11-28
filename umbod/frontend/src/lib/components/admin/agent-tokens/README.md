---
type: Software Module
title: Agent tokens workspace
description: Administration inventory and lifecycle forms for public MCP agent tokens.
---

# Source

- [Workspace](./AgentTokensWorkspace.svelte) — Shared record list with group, expiry, status, and lifecycle actions.
- [Dialog](./AgentTokenDialog.svelte) — Creation, rotation, revocation confirmation, and one-time token disclosure.
- [State](./agent-tokens-state.svelte.ts) — Metadata updates, mutation errors, and transient secret handling.
- [Workspace tests](./agent-tokens.dom.test.ts) — Lifecycle interactions and one-time secret visibility.
