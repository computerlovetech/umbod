---
type: Component Index
title: Reusable frontend components
description: Shared UI building blocks and styling foundations, with source links and guidance on when to reuse them.
tags:
  - frontend
  - components
  - design-consistency
---

# Reusable frontend components

## Buttons, fields, and forms

- [Button](src/lib/components/admin/shared/Button.svelte) — Standard action button; use primary, secondary, or danger variants and normal or compact sizing for consistent actions.
- [LoadingButton](src/lib/components/admin/shared/LoadingButton.svelte) — Async action button with delayed loading feedback; use for pending actions that must prevent repeated clicks.
- [AdminSaveAction](src/lib/components/admin/shared/AdminSaveAction.svelte) — Save button with status feedback; use when a save action needs loading, success, or error presentation.
- [AdminConfigurationField](src/lib/components/admin/shared/AdminConfigurationField.svelte) — Labelled text, password, or URL field; use for configuration inputs with helper text, validation, or existing-secret handling.
- [Select](src/lib/components/admin/shared/Select.svelte) — Controlled select or searchable combobox; use for keyboard-accessible choices, with parent-owned options and filtering.
- [AdminToggle](src/lib/components/admin/shared/AdminToggle.svelte) — Controlled checkbox or submit-button switch; use for activation and permission flags while the parent owns updates.
- [AdminFileUpload](src/lib/components/admin/shared/AdminFileUpload.svelte) — Single-file picker/drop field with size and type checks; use for file selection, noting its fixed JSON marker.
- [Form](src/lib/components/admin/shared/Form.svelte) — Scrollable fields and optional action footer; use for forms compatible with its attached administration submission integration.
- [CopyableValue](src/lib/components/admin/connectors/CopyableValue.svelte) — Value display with clipboard action and feedback; use for copyable identifiers or URIs within a toast-provider scope.

## Menus and dialogs

- [ActionMenu](src/lib/components/shared/ActionMenu.svelte) — Keyboard-accessible popup menu; use for contextual actions with custom trigger and menu content.
- [AdminSidebarActionMenu](src/lib/components/admin/shared/AdminSidebarActionMenu.svelte) — Ellipsis-trigger wrapper around ActionMenu; use for compact contextual actions in lists and sidebars.
- [AdminModalShell](src/lib/components/admin/shared/AdminModalShell.svelte) — Modal-styled surface with heading and dismissal; use with care: it is not native dialog and provides no focus trap or restoration.
- [Native dialog attachment](src/lib/components/shared/dialogs/native-dialog.ts) — Shared native-dialog lifecycle and initial-focus mechanics; use when composing a native dialog rather than duplicating its setup.

## Loading, notifications, and values

- [DelayedSpinner](src/lib/components/admin/shared/DelayedSpinner.svelte) — Delayed, labelled loading indicator; use for inline or standalone pending states without short-operation flicker.
- [DelayedLoadingOverlay](src/lib/components/admin/shared/DelayedLoadingOverlay.svelte) — Delayed loading scrim around content; use for visual pending feedback, not input blocking; currently has no production consumer.
- [ToastProvider](src/lib/components/feedback/ToastProvider.svelte) — Notification context and rendering scope; use around application content, where it is already mounted by the root layout.
- [Toast API](src/lib/components/feedback/index.ts) — Public provider, useToast, and notification types; use to send success, warning, or error messages from descendants.
- [ToastRegion](src/lib/components/feedback/ToastRegion.svelte) — Dismissible notification presenter with status/alert semantics; normally use through ToastProvider rather than mounting separately.
- [DateTimeView](src/lib/components/shared/DateTimeView.svelte) — Consistent English/UTC timestamp display; use for dates with exact source values available on hover.

## Layout and identity

- [AdminSplitWorkspace](src/lib/components/admin/shared/AdminSplitWorkspace.svelte) — Responsive master/detail surface; use for a labelled selector sidebar and detail pane across workspace features.
- [AdminStatCard](src/lib/components/admin/shared/AdminStatCard.svelte) — Label/value metric surface; use for summary statistics within a definition list.
- [CapabilityCatalogGrid](src/lib/components/admin/shared/CapabilityCatalogGrid.svelte) — Responsive list grid; use to arrange capability cards consistently, supplying list items as content.
- [ScrollableToolCatalog](src/lib/components/admin/shared/ScrollableToolCatalog.svelte) — Height-bounded tool-list region; use for independently scrolling tool catalogues with a stable scrollbar gutter.
- [WorkspaceShell](src/lib/components/shared/workspace/WorkspaceShell.svelte) — Application navigation, account, and logout frame; use for top-level workspace sections rather than a generic content container.
- [AccountPicture](src/lib/components/header/AccountPicture.svelte) — Account image with accessible placeholder; use for consistent user identity imagery in headers and navigation.

## Connector and catalogue presentation

- [ConnectorIcon](src/lib/components/admin/connectors/ConnectorIcon.svelte) — Decorative image or initials in standard sizes; use for connector identity, with accessible naming supplied elsewhere.
- [ConnectorSidebarList](src/lib/components/admin/connectors/ConnectorSidebarList.svelte) — Controlled connector selector with metadata and action slots; use for connector lists without coupling presentation to inventory fetching.
- [ConnectorDetailSummary](src/lib/components/admin/connectors/ConnectorDetailSummary.svelte) — Connector header and slotted detail layout; use for consistent connector identity, descriptions, and technical details.
- [ConnectorDetailItem](src/lib/components/admin/connectors/ConnectorDetailItem.svelte) — Definition-list label/value row with indicator tones; use for connector summary or technical-detail properties.
- [ConnectorListEmptyState](src/lib/components/admin/connectors/ConnectorListEmptyState.svelte) — Message-only empty-list surface; use for consistent empty connector catalogue states.
- [AdminPublicationStatus](src/lib/components/admin/shared/AdminPublicationStatus.svelte) — Publication-status pill; use for published, draft, or unconfigured states, not as a general-purpose badge.
- [CatalogControls](src/lib/components/admin/shared/CatalogControls.svelte) — Controlled search/filter/page-size toolbar; use for tool or operation catalogues with parent-owned filtering and counts.
- [CatalogPagination](src/lib/components/admin/shared/CatalogPagination.svelte) — Controlled previous/next navigation with page count; use for paged catalogues while the parent owns navigation.
- [ToolSaveBar](src/lib/components/admin/connectors/ToolSaveBar.svelte) — Dirty/pending save-status strip with action content; use for unsaved tool, prompt, or resource catalogue changes.
- [InvocationPolicyControl](src/lib/components/admin/connectors/InvocationPolicyControl.svelte) — Direct/approval policy selector with conflict feedback; use for administrator-managed connector invocation policies.
- [ConnectionStatusBadge](src/lib/components/personal-connections/ConnectionStatusBadge.svelte) — Compact or full personal-access status; use for connection cards and connector selector metadata.

## Tool presentation

- [ToolCard](src/lib/components/shared/tools/ToolCard.svelte) — Neutral tool identity and card layout; use for tool listings with feature-owned content and action slots, not actor-specific wrappers.
- [ToolDescription](src/lib/components/shared/tools/ToolDescription.svelte) — Expandable tool description; use to keep long or multiline descriptions compact within tool cards.
- [ToolParameterDetails](src/lib/components/shared/tools/ToolParameterDetails.svelte) — Input parameter and schema presentation; use to show a tool's accepted arguments consistently.
- [ToolOutputSchemaDetails](src/lib/components/shared/tools/ToolOutputSchemaDetails.svelte) — Output schema disclosure; use to show a tool's declared result structure or missing declaration.

## Shared styling foundations

- [Theme tokens](src/lib/styles/admin.css) — Shared colours, radii, shadows, and focus styling; use the semantic --admin-* variables across features, not just administration.
- [Native button/link styling](src/lib/styles/admin.css) — Shared .admin-button styles; use for existing native button or action-link markup, separately from the Button component.
- [Page typography and back links](src/lib/styles/admin.css) — Shared .admin-title, .admin-lede, and .admin-back-link styles; use for consistent page introductions and back navigation.
- [Panels and messages](src/lib/styles/admin.css) — Shared .admin-panel and .admin-message variants; use for surfaces and inline feedback, supplying accessibility semantics separately.
- [Card links](src/lib/styles/admin.css) — Shared .admin-card-link styling; use for navigable cards with consistent borders and hover states.
- [Global baseline](src/app.css) — Application typography, page reset, and focus ring; use as the baseline rather than recreating global styles per feature.

## Scope and composition

- [Component modules](src/lib/components/README.md) — Browse all presentation modules; this index selects reusable building blocks rather than feature screens or actor-owned workflows.
- [Shared UI boundaries](../project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Use shared presentation for common mechanics; keep actor-specific policy and data loading in feature compositions.
