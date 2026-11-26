---
type: Component Reference
title: Domain components
description: Dashboard charts, insights, file previews, connector and tool presentation, and feature composition references.
---

# Domain components

- [Component index](../COMPONENT_INDEX.md) — Browse the other component categories.

## Dashboard visualizations

- [OutcomeRing](../src/lib/components/shared/dashboard/visualizations/OutcomeRing.svelte) — Tool-outcome ring and labelled counts from prepared projections; renders a neutral empty state, not an implied success rate.
- [OperationMixChart](../src/lib/components/shared/dashboard/visualizations/OperationMixChart.svelte) — Proportion bar with category labels, percentages and counts; caller supplies prepared operation totals and shares.
- [DailyActivityChart](../src/lib/components/shared/dashboard/visualizations/DailyActivityChart.svelte) — Stacked daily tool outcomes with hover/focus breakdowns and totals; caller supplies UTC labels and a positive axis maximum.
- [ToolRankingList](../src/lib/components/shared/dashboard/visualizations/ToolRankingList.svelte) — Ranked tool bars and counts with five static silhouettes when empty; caller owns sorting, filtering and limiting.

## Insights presentation

- [AnalyticsWorkspace](../src/lib/components/shared/analytics/AnalyticsWorkspace.svelte) — Log queries, aggregate results, and session drill-down; callers inject state with the correct data scope.
- [ReportsView](../src/lib/components/shared/agent-behaviour/ReportsView.svelte) — Diagnostic report filters and linked results with agent-reported triggers for personal and admin Insights.
- [ReportDetailView](../src/lib/components/shared/agent-behaviour/ReportDetailView.svelte) — Diagnostic report with saved evidence, criteria, and agent-reported trigger; callers provide read state and actions.

## Files presentation

- [CsvPreview](../src/lib/components/files/preview/CsvPreview.svelte) — Content-only comma-separated table; shows up to 200 rows and 50 columns without header guessing, with plain text fallback for malformed CSV.
- [TextPreview](../src/lib/components/files/preview/TextPreview.svelte) — Content-only read-only plain text; preserves whitespace, wraps long lines and never interprets HTML or Markdown.
- [ImagePreview](../src/lib/components/files/preview/ImagePreview.svelte) — Content-only responsive raster image; use with a prepared image data URL and an optional decode-failure callback.
- [PdfPreview](../src/lib/components/files/preview/PdfPreview.svelte) — Content-only PDF frame; use with a prepared PDF data URL and a browser with built-in PDF viewing.
- [MarkdownPreview](../src/lib/components/files/preview/MarkdownPreview.svelte) — Content-only Markdown with highlighted code and bounded Mermaid diagrams; hides front matter, escapes HTML, omits images and restricts links.
- [PermissionBadge](../src/lib/components/files/PermissionBadge.svelte) — Compact caller-permission summary for file and folder rows; accepts permissions only, without ownership or operation eligibility.
- [FileTypeIcon](../src/lib/components/files/FileTypeIcon.svelte) — Accessible file-format, folder and explicit home SVGs; groups MIME types and extensions without loading file contents.
- [NamespaceIcon](../src/lib/components/admin/filesystem/NamespaceIcon.svelte) — Decorative folder tile for shared namespace rows with a visible name.

## Connector and catalogue presentation

- [AddConnector](../src/lib/components/admin/connectors/AddConnector.svelte) — Persistent connector setup trigger and type picker; the active connector route supplies setup eligibility and opens its own form.
- [ConnectorIcon](../src/lib/components/admin/connectors/ConnectorIcon.svelte) — Decorative image or initials in standard sizes; use for connector identity, with accessible naming supplied elsewhere.
- [ConnectorSidebarList](../src/lib/components/admin/connectors/ConnectorSidebarList.svelte) — Controlled connector rows with optional linked peers; use to combine local selection and navigation in one sidebar.
- [UnifiedConnectorWorkspace](../src/lib/components/admin/connectors/UnifiedConnectorWorkspace.svelte) — Shared admin connector layout; use for mixed inventories with route-owned selection, details, and actions.
- [ConnectorDetailSummary](../src/lib/components/admin/connectors/ConnectorDetailSummary.svelte) — Connector header and optional technical-details disclosure; compose the reference list with connector-owned groups.
- [PersonalServerPolicyPanel](../src/lib/components/admin/personal-mcp-servers/PersonalServerPolicyPanel.svelte) — Admin-only OAuth configuration and check state alongside private user responsibilities.
- [ConnectorStatusOverview](../src/lib/components/admin/connectors/ConnectorStatusOverview.svelte) — Icon-led connector indicators with an optional spotlight; use with caller-selected status and context fields.
- [ConnectorReferenceGroup](../src/lib/components/admin/connectors/ConnectorReferenceGroup.svelte) — Titled definition-list section; use with technical-detail rows inside the connector reference list.
- [ConnectorDetailItem](../src/lib/components/admin/connectors/ConnectorDetailItem.svelte) — Definition-list label/value row with indicator tones; use for connector summary or technical-detail properties.
- [ConnectorListEmptyState](../src/lib/components/admin/connectors/ConnectorListEmptyState.svelte) — Empty connector split workspace with a centred sidebar icon, accessible message and blank detail pane; use for empty connector inventories.
- [AdminPublicationStatus](../src/lib/components/admin/shared/AdminPublicationStatus.svelte) — Publication-status pill; use for published, draft, or unconfigured states, not as a general-purpose badge.
- [CatalogControls](../src/lib/components/admin/shared/CatalogControls.svelte) — Controlled search/filter/page-size toolbar; use for tool or operation catalogues with parent-owned filtering and counts.
- [CatalogPagination](../src/lib/components/admin/shared/CatalogPagination.svelte) — Controlled previous/next navigation with page count; use for paged catalogues while the parent owns navigation.
- [ToolSaveBar](../src/lib/components/admin/connectors/ToolSaveBar.svelte) — Dirty/pending save-status strip with action content; use for unsaved tool, prompt, or resource catalogue changes.
- [InvocationPolicyControl](../src/lib/components/admin/connectors/InvocationPolicyControl.svelte) — Direct/approval policy selector with conflict feedback; use for administrator-managed connector invocation policies.
- [ConnectionStatusBadge](../src/lib/components/personal-connections/ConnectionStatusBadge.svelte) — Compact or full personal-access status; use for connection cards and connector selector metadata.

## Tool presentation

- [ToolCard](../src/lib/components/shared/tools/ToolCard.svelte) — Neutral tool identity and card layout; use for tool listings with feature-owned content and action slots, not actor-specific wrappers.
- [ToolDescription](../src/lib/components/shared/tools/ToolDescription.svelte) — Expandable tool description; use to keep long or multiline descriptions compact within tool cards.
- [ToolParameterDetails](../src/lib/components/shared/tools/ToolParameterDetails.svelte) — Input parameter and schema presentation; use to show a tool's accepted arguments consistently.
- [ToolOutputSchemaDetails](../src/lib/components/shared/tools/ToolOutputSchemaDetails.svelte) — Output schema disclosure; use to show a tool's declared result structure or missing declaration.

## Scope and composition

- [Namespace administration composition](../src/lib/components/admin/filesystem/README.md) — Feature-owned namespace inventory, metadata dialogs, and a separate group access editor; reuse the indexed controls, not the workflows.
- [Agent behaviour composition](../src/lib/components/admin/agent-behaviour/README.md) — Feature-owned pattern editing, global reporting switch, and report inspection; reuse the indexed controls, not the administrator workflows.
- [Dashboard composition](../src/lib/components/dashboard/README.md) — Separate feature-owned usage and connector pages; reuse indexed controls, not either page workflow.
- [Getting started composition](../src/lib/components/getting-started/README.md) — Feature-owned harness installer wizard and optional private script preparation.
- [Account settings composition](../src/lib/components/settings/README.md) — Feature-owned profile and personal access navigation, token management, and telemetry setup.
- [Files compositions](../src/lib/components/files/README.md) — Feature-owned Locations navigation, details, sharing and mutation workflows; reuse neutral layouts and controls, not these compositions.
- [Component modules](../src/lib/components/README.md) — Browse all presentation modules; this index selects reusable building blocks rather than feature screens or actor-owned workflows.
- [Shared UI boundaries](../../project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Use shared presentation for common mechanics; keep actor-specific policy and data loading in feature compositions.
