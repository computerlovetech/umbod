---
type: Component Reference
title: Workspace layout
description: Workspace frames, navigation, identity, dashboard layout, and shared styling foundations.
---

# Workspace layout

- [Component index](../COMPONENT_INDEX.md) — Browse the other component categories.

## Layout and identity

- [SetupProgress](../src/lib/components/admin/shared/SetupProgress.svelte) — Studio-style step indicator for guided setup; callers supply step labels and the current step, and own navigation.
- [PageContainer](../src/lib/components/shared/workspace/PageContainer.svelte) — Shared heading, optional actions and content slots for Files and Connectors; pair with the split workspace for sidebar/detail pages.
- [SubpageContainer](../src/lib/components/shared/workspace/SubpageContainer.svelte) — Shared page heading, optional introduction, action slot and content frame; use with feature-owned navigation and selected subpage content.
- [SubpageNavigation](../src/lib/components/shared/workspace/SubpageNavigation.svelte) — Horizontal links with current-page or parent-location semantics; parents supply routes, selection and eligibility.
- [InsightsFrame](../src/lib/components/shared/workspace/InsightsFrame.svelte) — Shared Insights heading and subpage layout; personal and admin callers supply links and content.
- [AdminSplitWorkspace](../src/lib/components/admin/shared/AdminSplitWorkspace.svelte) — Responsive master/detail surface with optional mobile sidebar drawer and flush detail padding.
- [AdminRecordList](../src/lib/components/admin/shared/AdminRecordList.svelte) — Responsive record list with identity, detail, and action slots; use for administration inventories with feature-owned actions.
- [AdminPermissionRow](../src/lib/components/admin/shared/AdminPermissionRow.svelte) — Responsive permission-list row with shared identity layout and feature-owned controls or expanded details.
- [CapabilityCatalogGrid](../src/lib/components/admin/shared/CapabilityCatalogGrid.svelte) — Responsive list grid; use to arrange capability cards consistently, supplying list items as content.
- [ScrollableToolCatalog](../src/lib/components/admin/shared/ScrollableToolCatalog.svelte) — Height-bounded tool-list region; use for independently scrolling tool catalogues with a stable scrollbar gutter.
- [WorkspaceShell](../src/lib/components/shared/workspace/WorkspaceShell.svelte) — Contextual sidebar with a mobile drawer, optional return link, account and logout; parents own destinations and eligibility.
- [AccountPicture](../src/lib/components/header/AccountPicture.svelte) — Account image with accessible placeholder; use for consistent user identity imagery in headers and navigation.

## Dashboard layout

- [DashboardContainer](../src/lib/components/shared/dashboard/DashboardContainer.svelte) — Named section with heading, caller-owned toolbar and footer; compose rows here without coupling layout to data loading.
- [DashboardRow](../src/lib/components/shared/dashboard/DashboardRow.svelte) — Twelve-track responsive row; use with DashboardColumn for aligned visual panels without fixed viewport heights.
- [DashboardColumn](../src/lib/components/shared/dashboard/DashboardColumn.svelte) — Explicit one-to-twelve span within DashboardRow; stacks below a 760px dashboard container width.
- [DashboardPanel](../src/lib/components/shared/dashboard/DashboardPanel.svelte) — Neutral panel with a level-three heading, metadata and optional actions; use within a labelled dashboard section.
- [DashboardPeriodSwitch](../src/lib/components/shared/dashboard/DashboardPeriodSwitch.svelte) — Controlled 7/30-day button group with pressed states; use for aligned dashboard period selection without a dropdown.

## Shared styling foundations

- [Theme tokens](../src/lib/styles/admin.css) — Shared colours, radii, shadows, and focus styling; use the semantic --admin-* variables across features, not just administration.
- [Insights styling](../src/lib/styles/insights.css) — Common headings, query-field layout, result frames and pagination for separate Insights views.
- [Subpage navigation styling](../src/lib/styles/subpage-navigation.css) — Underline presentation for route links and in-place tabs; preserves each control's navigation and keyboard semantics.
- [Page typography and back links](../src/lib/styles/admin.css) — Shared .admin-title, .admin-lede, and .admin-back-link styles; use for consistent page introductions and back navigation.
- [Panels and messages](../src/lib/styles/admin.css) — Shared .admin-panel and .admin-message variants; use for surfaces and inline feedback, supplying accessibility semantics separately.
- [Card links](../src/lib/styles/admin.css) — Shared .admin-card-link styling; use for navigable cards with consistent borders and hover states.
- [Global baseline](../src/app.css) — Application typography, page reset, and focus ring; use as the baseline rather than recreating global styles per feature.
