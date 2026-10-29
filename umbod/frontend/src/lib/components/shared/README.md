---
type: Software Module
title: "Shared components"
description: "Actor-independent presentation and interaction mechanics."
---

# Files

- [ActionMenu.svelte](./ActionMenu.svelte) — Controlled menu with typed trigger and content snippets, independent of actor policy or data.
- [action-menu-state.svelte.ts](./action-menu-state.svelte.ts) — Shared keyboard focus, dismissal and viewport positioning mechanics.
- [action-menu.test.ts](./action-menu.test.ts) — Keyboard movement, focus restoration, outside dismissal and administration compatibility tests.
- [DateTimeView.svelte](./DateTimeView.svelte) — Date and time display.
- [dialogs](./dialogs/README.md) — Native dialog lifecycle and focus mechanics.
- [mcp-setup/](./mcp-setup/) — Endpoint-driven client setup instructions.
- [tools](./tools/README.md) — Neutral tool cards and schema presenters.
- [workspace/](./workspace/) — Navigation, account and logout shell.

# Architecture

- [ADR-007: Actor-Specific Composition](../../../../../project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Shared changes deliberately affect multiple consumers.
