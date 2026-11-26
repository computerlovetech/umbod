---
type: Software Module
title: "Shared components"
description: "Actor-independent presentation and interaction mechanics."
---

# Files

- [Checkbox.svelte](./Checkbox.svelte) — Controlled labelled native checkbox with shared selection styling, native attributes and caller-owned updates.
- [checkbox.dom.test.ts](./checkbox.dom.test.ts) — Label activation, controlled updates, disabled behavior and native input integration.

- [TextAreaField.svelte](./TextAreaField.svelte) — Controlled labelled multiline input forwarding native attributes and events.
- [text-area-field.dom.test.ts](./text-area-field.dom.test.ts) — Multiline values, validation, accessibility, events and caller-owned state.
- [Field styling](../../styles/form-fields.css) — Shared labels, control appearance, validation and focus rings for plain and configuration fields.

- [SegmentedRadio.svelte](./SegmentedRadio.svelte) — Controlled segmented native radios with normal or compact sizing, visible choices, unique group names and parent-owned selection.
- [segmented-radio.dom.test.ts](./segmented-radio.dom.test.ts) — Visible choices, native grouping, disabled interaction, size variants and controlled selection tests.
- [TextField.svelte](./TextField.svelte) — Controlled labelled plain text input forwarding native attributes and events without credential-specific behavior.
- [text-field.dom.test.ts](./text-field.dom.test.ts) — Native input attributes, autofill opt-outs, event forwarding and caller-owned values.

- [ActionMenu.svelte](./ActionMenu.svelte) — Controlled menu with typed snippets and a native disabled trigger, independent of actor policy or data.
- [action-menu-state.svelte.ts](./action-menu-state.svelte.ts) — Shared keyboard focus, dismissal and viewport positioning mechanics.
- [action-menu.test.ts](./action-menu.test.ts) — Keyboard movement, focus restoration, outside dismissal and administration compatibility tests.
- [action-menu-disabled.dom.test.ts](./action-menu-disabled.dom.test.ts) — Disabled native trigger, hidden popup and guarded pointer/keyboard interaction.
- [PlusIcon.svelte](./PlusIcon.svelte) — Decorative leading plus for labeled creation buttons.
- [DateTimeView.svelte](./DateTimeView.svelte) — Date and time display.
- [ModalShell.svelte](./ModalShell.svelte) — Native modal with a shared heading, close control, guarded dismissal, and initial focus.
- [Modal DOM tests](./modal-shell.dom.test.ts) — Accessible close control, native cancellation guards, backdrop hit testing, and initial focus.
- [Modal test harness](./modal-shell.test-support.svelte) — Mounted modal form for dismissal and reactive guard checks.
- [Dashboard presentation](./dashboard/README.md) — Responsive container, rows, columns and visual panel surfaces without data-loading dependencies.
- [dialogs](./dialogs/README.md) — Native dialog lifecycle and focus mechanics.
- [tools](./tools/README.md) — Neutral tool cards and schema presenters.
- [Workspace](./workspace/README.md) — Application shell and neutral subpage containers and navigation.

# Architecture

- [ADR-007: Actor-Specific Composition](../../../../../project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Shared changes deliberately affect multiple consumers.
