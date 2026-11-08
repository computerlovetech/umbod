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
- [ModalShell.svelte](./ModalShell.svelte) — Native modal with a shared heading, close control, guarded dismissal, and initial focus.
- [Modal DOM tests](./modal-shell.dom.test.ts) — Accessible close control, native cancellation guards, backdrop hit testing, and initial focus.
- [Modal test harness](./modal-shell.test-support.svelte) — Mounted modal form for dismissal and reactive guard checks.
- [dialogs](./dialogs/README.md) — Native dialog lifecycle and focus mechanics.
- [tools](./tools/README.md) — Neutral tool cards and schema presenters.
- [Workspace](./workspace/README.md) — Application shell and neutral subpage containers and navigation.

# Architecture

- [ADR-007: Actor-Specific Composition](../../../../../project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Shared changes deliberately affect multiple consumers.
