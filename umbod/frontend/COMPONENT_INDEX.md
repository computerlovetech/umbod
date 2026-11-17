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

- [TextAreaField](src/lib/components/shared/TextAreaField.svelte) — Controlled labelled multiline input with native attributes and events; uses the same field and focus styling as plain and configuration text inputs.

- [TextField](src/lib/components/shared/TextField.svelte) — Controlled labelled plain text input with native attribute and event forwarding; use for non-credential text without configuration-secret behavior.

- [Button](src/lib/components/admin/shared/Button.svelte) — Native action button with primary, secondary, danger, quiet, compact, and icon-only presentation; forwards native attributes, events, and attachments.
- [ButtonLink](src/lib/components/admin/shared/ButtonLink.svelte) — Native navigation anchor with canonical action styling; use for action-like links without replacing href semantics.
- [LoadingButton](src/lib/components/admin/shared/LoadingButton.svelte) — Button with delayed loading feedback, native attribute forwarding, and immediate pending protection; supports the same variants and sizes.
- [AdminSaveAction](src/lib/components/admin/shared/AdminSaveAction.svelte) — Save button with status feedback; use when a save action needs loading, success, or error presentation.
- [AdminConfigurationField](src/lib/components/admin/shared/AdminConfigurationField.svelte) — Labelled text, password, or URL field; use for configuration inputs with helper text, validation, or existing-secret handling.
- [SegmentedRadio](src/lib/components/shared/SegmentedRadio.svelte) — Controlled native radios with normal or compact sizing; use for a short set of visible, mutually exclusive choices and parent-owned updates.
- [Select](src/lib/components/admin/shared/Select.svelte) — Controlled select or searchable combobox; use for keyboard-accessible choices, with parent-owned options and filtering.
- [Checkbox](src/lib/components/shared/Checkbox.svelte) — Controlled labelled native checkbox; use for selections and approvals with parent-owned updates and native input attributes.
- [AdminToggle](src/lib/components/admin/shared/AdminToggle.svelte) — Controlled switch or submit-button switch; use for activation settings while the parent owns updates.
- [AdminFileUpload](src/lib/components/admin/shared/AdminFileUpload.svelte) — Single-file picker/drop field with size and type checks; use for file selection, noting its fixed JSON marker.
- [QueryPanel](src/lib/components/shared/workspace/QueryPanel.svelte) — Collapsed native query editor; callers own parameters, reset, submission and loading.
- [Form](src/lib/components/admin/shared/Form.svelte) — Scrollable fields and optional action footer; use for forms compatible with its attached administration submission integration.
- [CopyableValue](src/lib/components/admin/connectors/CopyableValue.svelte) — Value display with clipboard action and feedback; use for copyable identifiers or URIs within a toast-provider scope.

## Menus and dialogs

- [ActionMenu](src/lib/components/shared/ActionMenu.svelte) — Keyboard-accessible popup menu; use for contextual actions with custom trigger and menu content.
- [AdminSidebarActionMenu](src/lib/components/admin/shared/AdminSidebarActionMenu.svelte) — Ellipsis-trigger wrapper around ActionMenu; use for compact contextual actions in lists and sidebars.
- [ModalShell](src/lib/components/shared/ModalShell.svelte) — Native modal with heading and upper-right close button; use for dialogs with guarded dismissal and caller-selected initial focus.
- [Native dialog attachment](src/lib/components/shared/dialogs/native-dialog.ts) — Native-dialog lifecycle and Cancel/Close focus fallbacks; avoids automatic field preselection unless the caller requests it.

## Loading, notifications, and values

- [DelayedSpinner](src/lib/components/admin/shared/DelayedSpinner.svelte) — Delayed, labelled loading indicator; use for inline or standalone pending states without short-operation flicker.
- [DelayedLoadingOverlay](src/lib/components/admin/shared/DelayedLoadingOverlay.svelte) — Delayed loading scrim around content; used for retained Files navigation feedback, not input blocking.
- [ToastProvider](src/lib/components/feedback/ToastProvider.svelte) — Notification context and rendering scope; use around application content, where it is already mounted by the root layout.
- [Toast API](src/lib/components/feedback/index.ts) — Public provider, useToast, and notification types; use to send success, warning, or error messages from descendants.
- [ToastRegion](src/lib/components/feedback/ToastRegion.svelte) — Labelled notification region with dismissible status/alert messages; normally use through ToastProvider rather than separately.
- [DateTimeView](src/lib/components/shared/DateTimeView.svelte) — Consistent English/UTC timestamp display; use for dates with exact source values available on hover.

## Layout and identity

- [PageContainer](src/lib/components/shared/workspace/PageContainer.svelte) — Shared heading, optional actions and content slots for Files and Connectors; pair with the split workspace for sidebar/detail pages.
- [SubpageContainer](src/lib/components/shared/workspace/SubpageContainer.svelte) — Shared page heading, optional introduction, action slot and content frame; use with feature-owned navigation and selected subpage content.
- [SubpageNavigation](src/lib/components/shared/workspace/SubpageNavigation.svelte) — Horizontal links with current-page or parent-location semantics; parents supply routes, selection and eligibility.

- [AdminSplitWorkspace](src/lib/components/admin/shared/AdminSplitWorkspace.svelte) — Responsive master/detail surface; use for sidebar/detail workspaces, with optional --split-workspace-detail-padding for flush content.
- [CapabilityCatalogGrid](src/lib/components/admin/shared/CapabilityCatalogGrid.svelte) — Responsive list grid; use to arrange capability cards consistently, supplying list items as content.
- [ScrollableToolCatalog](src/lib/components/admin/shared/ScrollableToolCatalog.svelte) — Height-bounded tool-list region; use for independently scrolling tool catalogues with a stable scrollbar gutter.
- [WorkspaceShell](src/lib/components/shared/workspace/WorkspaceShell.svelte) — Contextual sidebar, optional section heading and return link, account and logout frame; parents own destinations and eligibility.
- [AccountPicture](src/lib/components/header/AccountPicture.svelte) — Account image with accessible placeholder; use for consistent user identity imagery in headers and navigation.

## Dashboard layout

- [DashboardContainer](src/lib/components/shared/dashboard/DashboardContainer.svelte) — Named section with heading, caller-owned toolbar and footer; compose rows here without coupling layout to data loading.
- [DashboardRow](src/lib/components/shared/dashboard/DashboardRow.svelte) — Twelve-track responsive row; use with DashboardColumn for aligned visual panels without fixed viewport heights.
- [DashboardColumn](src/lib/components/shared/dashboard/DashboardColumn.svelte) — Explicit one-to-twelve span within DashboardRow; stacks below a 760px dashboard container width.
- [DashboardPanel](src/lib/components/shared/dashboard/DashboardPanel.svelte) — Neutral panel with a level-three heading, metadata and optional actions; use within a labelled dashboard section.

- [DashboardPeriodSwitch](src/lib/components/shared/dashboard/DashboardPeriodSwitch.svelte) — Controlled 7/30-day button group with pressed states; use for aligned dashboard period selection without a dropdown.

## Dashboard visualizations

- [OutcomeRing](src/lib/components/shared/dashboard/visualizations/OutcomeRing.svelte) — Tool-outcome ring and labelled counts from prepared projections; renders a neutral empty state, not an implied success rate.
- [OperationMixChart](src/lib/components/shared/dashboard/visualizations/OperationMixChart.svelte) — Proportion bar with category labels, percentages and counts; caller supplies prepared operation totals and shares.
- [DailyActivityChart](src/lib/components/shared/dashboard/visualizations/DailyActivityChart.svelte) — Stacked daily tool outcomes with accessible per-day values; caller supplies UTC labels and a positive axis maximum.
- [ToolRankingList](src/lib/components/shared/dashboard/visualizations/ToolRankingList.svelte) — Ranked tool bars and counts with five static silhouettes when empty; caller owns sorting, filtering and limiting.

## Files presentation

- [CsvPreview](src/lib/components/files/preview/CsvPreview.svelte) — Content-only comma-separated table; shows up to 200 rows and 50 columns without header guessing, with plain text fallback for malformed CSV.

- [TextPreview](src/lib/components/files/preview/TextPreview.svelte) — Content-only read-only plain text; preserves whitespace, wraps long lines and never interprets HTML or Markdown.

- [ImagePreview](src/lib/components/files/preview/ImagePreview.svelte) — Content-only responsive raster image; use with a prepared image data URL and an optional decode-failure callback.

- [PdfPreview](src/lib/components/files/preview/PdfPreview.svelte) — Content-only PDF frame; use with a prepared PDF data URL and a browser with built-in PDF viewing.

- [MarkdownPreview](src/lib/components/files/preview/MarkdownPreview.svelte) — Content-only Markdown with highlighted code and bounded Mermaid diagrams; hides front matter, escapes HTML, omits images and restricts links.

- [PermissionBadge](src/lib/components/files/PermissionBadge.svelte) — Compact caller-permission summary for file and folder rows; accepts permissions only, without ownership or operation eligibility.
- [FileTypeIcon](src/lib/components/files/FileTypeIcon.svelte) — Accessible file-format, folder and explicit home SVGs; groups MIME types and extensions without loading file contents.

## Connector and catalogue presentation

- [ConnectorIcon](src/lib/components/admin/connectors/ConnectorIcon.svelte) — Decorative image or initials in standard sizes; use for connector identity, with accessible naming supplied elsewhere.
- [ConnectorSidebarList](src/lib/components/admin/connectors/ConnectorSidebarList.svelte) — Controlled connector selector with metadata and action slots; use for connector lists without coupling presentation to inventory fetching.
- [ConnectorDetailSummary](src/lib/components/admin/connectors/ConnectorDetailSummary.svelte) — Connector header and slotted detail layout; use for consistent connector identity, descriptions, and technical details.
- [ConnectorDetailItem](src/lib/components/admin/connectors/ConnectorDetailItem.svelte) — Definition-list label/value row with indicator tones; use for connector summary or technical-detail properties.
- [ConnectorListEmptyState](src/lib/components/admin/connectors/ConnectorListEmptyState.svelte) — Empty connector split workspace with a centred sidebar icon, accessible message and blank detail pane; use for empty connector inventories.
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

- [Form field styling](src/lib/styles/form-fields.css) — Non-shrinking field stacks, canonical text controls, validation and focus rings for TextField, TextAreaField and AdminConfigurationField.

- [Theme tokens](src/lib/styles/admin.css) — Shared colours, radii, shadows, and focus styling; use the semantic --admin-* variables across features, not just administration.
- [Insights styling](src/lib/styles/insights.css) — Common headings, query-field layout, result frames and pagination for separate Insights views.
- [Subpage navigation styling](src/lib/styles/subpage-navigation.css) — Underline presentation for route links and in-place tabs; preserves each control's navigation and keyboard semantics.
- [Canonical button styling](src/lib/styles/buttons.css) — Shared visual rules for Button and ButtonLink; use the components for actions and action-like navigation, respectively.
- [Page typography and back links](src/lib/styles/admin.css) — Shared .admin-title, .admin-lede, and .admin-back-link styles; use for consistent page introductions and back navigation.
- [Panels and messages](src/lib/styles/admin.css) — Shared .admin-panel and .admin-message variants; use for surfaces and inline feedback, supplying accessibility semantics separately.
- [Card links](src/lib/styles/admin.css) — Shared .admin-card-link styling; use for navigable cards with consistent borders and hover states.
- [Global baseline](src/app.css) — Application typography, page reset, and focus ring; use as the baseline rather than recreating global styles per feature.

## Scope and composition

- [Namespace administration composition](src/lib/components/admin/filesystem/README.md) — Feature-owned namespace list and create/edit dialogs; reuse shared modal and form controls, not this administration workflow.

- [Agent behaviour composition](src/lib/components/admin/agent-behaviour/README.md) — Feature-owned pattern editing and report inspection; reuse its canonical controls, not these administrator workflows.

- [Dashboard composition](src/lib/components/dashboard/README.md) — Separate feature-owned usage and connector pages; reuse indexed controls, not either page workflow.

- [Getting started composition](src/lib/components/getting-started/README.md) — Feature-owned platform installers, harness onboarding and personal-token workflows; reuse its neutral controls, not the complete page.

- [Log analytics composition](src/lib/components/admin/analytics/README.md) — Feature-owned queries, results and session inspection; excluded because it owns administrator analytics workflows.

- [Files compositions](src/lib/components/files/README.md) — Feature-owned Locations navigation, details, sharing and mutation workflows; reuse neutral layouts and controls, not these compositions.

- [Component modules](src/lib/components/README.md) — Browse all presentation modules; this index selects reusable building blocks rather than feature screens or actor-owned workflows.
- [Shared UI boundaries](../project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Use shared presentation for common mechanics; keep actor-specific policy and data loading in feature compositions.
