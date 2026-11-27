---
type: Component Reference
title: Dialogs and feedback
description: Menus, dialogs, loading indicators, notifications, and copyable or formatted values.
---

# Dialogs and feedback

- [Component index](../COMPONENT_INDEX.md) — Browse the other component categories.

## Menus and dialogs

- [ActionMenu](../src/lib/components/shared/ActionMenu.svelte) — Keyboard-accessible popup with icon or full-width triggers and reduced-motion support; use for contextual links and actions.
- [AdminSidebarActionMenu](../src/lib/components/admin/shared/AdminSidebarActionMenu.svelte) — Ellipsis-trigger wrapper around ActionMenu; use for compact contextual actions in lists and sidebars.
- [ModalShell](../src/lib/components/shared/ModalShell.svelte) — Native modal with heading and upper-right close button; use for dialogs with guarded dismissal and caller-selected initial focus.
- [Native dialog attachment](../src/lib/components/shared/dialogs/native-dialog.ts) — Native-dialog lifecycle and Cancel/Close focus fallbacks; avoids automatic field preselection unless the caller requests it.

## Loading, notifications, and values

- [DelayedSpinner](../src/lib/components/admin/shared/DelayedSpinner.svelte) — Delayed, labelled loading indicator; use for inline or standalone pending states without short-operation flicker.
- [DelayedLoadingOverlay](../src/lib/components/admin/shared/DelayedLoadingOverlay.svelte) — Delayed loading scrim around content; used for retained Files navigation feedback, not input blocking.
- [ToastProvider](../src/lib/components/feedback/ToastProvider.svelte) — Notification context and rendering scope; use around application content, where it is already mounted by the root layout.
- [Toast API](../src/lib/components/feedback/index.ts) — Public provider, useToast, and notification types; use to send success, warning, or error messages from descendants.
- [ToastRegion](../src/lib/components/feedback/ToastRegion.svelte) — Labelled notification region with dismissible status/alert messages; normally use through ToastProvider rather than separately.
- [DateTimeView](../src/lib/components/shared/DateTimeView.svelte) — Consistent English/UTC timestamp display; use for dates with exact source values available on hover.
- [CopyableValue](../src/lib/components/admin/connectors/CopyableValue.svelte) — Value display with clipboard action and feedback; use for copyable identifiers or URIs within a toast-provider scope.
