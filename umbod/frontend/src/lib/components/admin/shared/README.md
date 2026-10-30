---
type: Software Module
title: Shared administration controls
description: Reusable administration presentation and interaction controls.
---

# Selection

- [Select](Select.svelte) — Controlled button or searchable combobox with dialog-aware popup positioning.
- [Select state](select-state.svelte.ts) — Current-input selection, enabled cursor navigation, and viewport geometry.
- [State tests](select-state.test.ts) — Controlled updates, disabled choices, navigation, and placement behavior.
- [DOM tests](select.dom.test.ts) — Mounted search, selection, dismissal, keyboard, and stale-choice guards.
- [Test model](select.test-support.svelte.ts) — Reactive controlled inputs for mounted selection tests.
- [Test harness](SelectTestHarness.test-support.svelte) — Selection inside a dialog form and disableable fieldset.

# Forms and layout

- [Form](Form.svelte) — Shared form rendering and pending feedback.
- [Button](Button.svelte) — Shared button presentation.
- [Modal shell](AdminModalShell.svelte) — Native dialog composition.
- [Configuration field](AdminConfigurationField.svelte) — Configuration input rendering.
- [Split workspace](AdminSplitWorkspace.svelte) — Shared master-detail layout.

# Architecture

- [State ownership](../../../../../../project/architecture-records/ADR-011-state-ownership-and-rendering-boundaries.md) — State and rendering responsibilities.
