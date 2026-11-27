---
type: Component Reference
title: Forms and controls
description: Buttons, fields, selection controls, form containers, and their shared styling.
---

# Forms and controls

- [Component index](../COMPONENT_INDEX.md) — Browse the other component categories.

## Buttons, fields, and forms

- [TextAreaField](../src/lib/components/shared/TextAreaField.svelte) — Controlled labelled multiline input with native attributes and events; uses the same field and focus styling as plain and configuration text inputs.
- [TextField](../src/lib/components/shared/TextField.svelte) — Controlled labelled plain text input with native attribute and event forwarding; use for non-credential text without configuration-secret behavior.
- [Button](../src/lib/components/admin/shared/Button.svelte) — Native action button; use `variant="soft"` for a tinted secondary action or `variant="unstyled"` for a control with its own styling.
- [PlusIcon](../src/lib/components/shared/PlusIcon.svelte) — Decorative leading plus for labeled buttons that start creating a new item, not form submit buttons.
- [ButtonLink](../src/lib/components/admin/shared/ButtonLink.svelte) — Native navigation anchor with the same presentation variants as Button; use for action-like links that retain href semantics.
- [LoadingButton](../src/lib/components/admin/shared/LoadingButton.svelte) — Button with delayed loading feedback, native attribute forwarding, and immediate pending protection; supports the same variants and sizes.
- [AdminSaveAction](../src/lib/components/admin/shared/AdminSaveAction.svelte) — Save button with status feedback; use when a save action needs loading, success, or error presentation.
- [AdminConfigurationField](../src/lib/components/admin/shared/AdminConfigurationField.svelte) — Labelled text, password, or URL field; use for configuration inputs with helper text, validation, or existing-secret handling.
- [SegmentedRadio](../src/lib/components/shared/SegmentedRadio.svelte) — Controlled native radios with normal or compact sizing; use for a short set of visible, mutually exclusive choices and parent-owned updates.
- [Select](../src/lib/components/admin/shared/Select.svelte) — Keyboard-accessible select or searchable combobox with parent-owned options and filtering; supports an inline label for settings rows.
- [Checkbox](../src/lib/components/shared/Checkbox.svelte) — Controlled labelled native checkbox; use for selections and approvals with parent-owned updates and native input attributes.
- [AdminToggle](../src/lib/components/admin/shared/AdminToggle.svelte) — Controlled switch or submit-button switch; use for activation settings while the parent owns updates.
- [AdminToggleSetting](../src/lib/components/admin/shared/AdminToggleSetting.svelte) — Settings card with a described toggle, visible On/Off state, and optional metadata and notices.
- [AdminSettingsActions](../src/lib/components/admin/shared/AdminSettingsActions.svelte) — Save and discard row for staged settings; callers own drafts, publishing, and conflict resolution.
- [AdminFileUpload](../src/lib/components/admin/shared/AdminFileUpload.svelte) — Single-file picker/drop field with size and type checks; use for file selection, noting its fixed JSON marker.
- [Disclosure](../src/lib/components/shared/Disclosure.svelte) — Keyboard-accessible inline disclosure with retained content, reduced-motion-aware transitions, and local or caller-controlled expansion.
- [QueryPanel](../src/lib/components/shared/workspace/QueryPanel.svelte) — Collapsible query editor; callers own parameters, reset, submission and loading.
- [Form](../src/lib/components/admin/shared/Form.svelte) — Scrollable fields and optional action footer; use for forms compatible with its attached administration submission integration.

## Shared form and button styles

- [Form field styling](../src/lib/styles/form-fields.css) — Non-shrinking field stacks, canonical text controls, validation and focus rings for TextField, TextAreaField and AdminConfigurationField.
- [Canonical button styling](../src/lib/styles/buttons.css) — Shared visual rules for Button and ButtonLink; use the components for actions and action-like navigation, respectively.
