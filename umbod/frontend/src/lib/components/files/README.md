---
type: Software Module
title: "Files components"
description: "Namespace browsing, per-item sharing, node details, folder creation and single-file uploads."
---

# Files

- [preview/README.md](./preview/README.md) — Filetype-adapted content previews, initially safe Markdown, with loading and recovery presentation.

- [NodeActions.svelte](./NodeActions.svelte) — Files-owned disabled/context-scoped header and row menus, with details, sharing, mutations and operation-owned dialogs.
- [NodeDetailsDialog.svelte](./NodeDetailsDialog.svelte) — Node metadata, containing namespace identity and five caller permissions; the namespace label is not a complete audience.
- [PermissionBadge.svelte](./PermissionBadge.svelte) — Neutral permissions-only badge used beside file and folder row names.
- [permission-label.ts](./permission-label.ts) — Exact caller permission combinations summarized without implying unsupported operations.
- [permission-label.test.ts](./permission-label.test.ts) — Read-only, editable, discover-only and custom permission label cases.
- [node-details.dom.test.ts](./node-details.dom.test.ts) — Details eligibility, fields, live updates, access loss, navigation cleanup, personal root protection and focus restoration.
- [node-details-inputs.svelte.test-support.ts](./node-details-inputs.svelte.test-support.ts) — Reactive live node inputs for isolated details interaction tests.
- [NodeSharingDialog.svelte](./NodeSharingDialog.svelte) — Group/user recipient search, permission drafts, recursive scope and conditional sharing saves.
- [node-sharing.dom.test.ts](./node-sharing.dom.test.ts) — Recipient selection, scope, switching, pending guards, focus and direct UUID access without namespace-root membership.
- [NodeActionIcon.svelte](./NodeActionIcon.svelte) — Decorative icons for filesystem menu actions and recovery entries.
- [node-actions.dom.test.ts](./node-actions.dom.test.ts) — Single row trigger, icon-labelled actions and deletion lifecycle interactions.
- [node-actions-state.test.ts](./node-actions-state.test.ts) — Discover-only eligibility, live authoritative node reads, menu dismissal and explicit details closure.
- [node-actions-state.svelte.ts](./node-actions-state.svelte.ts) — Live details selection, menu eligibility, action dispatch and persistent-trigger focus restoration.
- [NodeDescriptionDialog.svelte](./NodeDescriptionDialog.svelte) — Native description editor with pending guards and explicit conflict recovery.
- [NodeUpdateDialog.svelte](./NodeUpdateDialog.svelte) — Files-owned rename and picker/native move reviews with namespace-access warnings and explicit confirmation.
- [node-update.dom.test.ts](./node-update.dom.test.ts) — Rename, destination selection, branch retries, cancellation and empty-folder keyboard focus interactions.
- [folder-picker-focus-state.svelte.ts](./folder-picker-focus-state.svelte.ts) — Keeps focused folder disclosures mounted until blur when asynchronous loading reveals an empty branch.

- [files-components.test.ts](./files-components.test.ts) — Stable Files heading, coherent browse loading, fail-closed paths, navigation and creation form tests.
- [files-navigation-rendering.dom.test.ts](./files-navigation-rendering.dom.test.ts) — Retained controls, SVGs and rows, inert pending content and refresh-scoped menu/details dismissal.
- [files-route-navigation.dom.test.ts](./files-route-navigation.dom.test.ts) — Same-target hash, unrelated query and personal-root alias navigation preserve creation drafts without refetching.
- [files-description.dom.test.ts](./files-description.dom.test.ts) — Description editing, clear, cancel, pending, denied, conflict and creation input interactions.
- [Shared page container](../shared/workspace/PageContainer.svelte) — Common header, action and content slots shared with Connectors; Files owns action labels and eligibility.
- [FilesContent.svelte](./FilesContent.svelte) — Stable Files heading and retained actions above Locations, with inert pending listings, delayed overlay feedback and upload drops.
- [FilesLocations.svelte](./FilesLocations.svelte) — Feature-owned grouped namespace links, selected location checks and independent discovery recovery.
- [files-locations.dom.test.ts](./files-locations.dom.test.ts) — Native grouped links, discovery recovery, reactive labels and stable rail/detail frames through loading and previews.
- [FileTypeIcon.svelte](./FileTypeIcon.svelte) — Accessible format, folder and explicit home icons shared by list rows and filename-based drag previews.
- [file-type-icons.ts](./file-type-icons.ts) — Common format groups and explicit home SVGs; specific MIME types precede extensions, with safe generic and text fallbacks.
- [file-type-icons.test.ts](./file-type-icons.test.ts) — Grouped extensions, MIME precedence, normalization, unknown formats and directory overrides.
- [file-type-icon.dom.test.ts](./file-type-icon.dom.test.ts) — Accessible category rendering and in-place row icon changes after a filename extension is renamed.
- [file-drag-move.dom.test.ts](./file-drag-move.dom.test.ts) — Drag previews, move review confirmation/cancellation, reconciliation, focus, recovery and external upload isolation.
- [FileUploadForm.svelte](./FileUploadForm.svelte) — Native upload modal with distinct selected-file card, thumbnail, replacement picker and server-validated feedback.
- [file-thumbnail-state.svelte.ts](./file-thumbnail-state.svelte.ts) — Scoped raster thumbnail URLs with decode-failure fallback and attachment cleanup.
- [file-upload-form.dom.test.ts](./file-upload-form.dom.test.ts) — Selection, replacement, removal focus, thumbnail cleanup and locked upload interactions.
- [file-upload-form.test.ts](./file-upload-form.test.ts) — Modal semantics, accessible selection, validation and pending states.
- [FileDeletionDialog.svelte](./FileDeletionDialog.svelte) — Files-owned permanent removal confirmation using shared native-dialog mechanics.
- [file-deletion.test.ts](./file-deletion.test.ts) — Row and details eligibility, accessible filename-specific confirmation and danger action presentation tests.
- [FilesPage.svelte](./FilesPage.svelte) — Files content with semantic route guards, frame-scoped identity and identity-fenced request lifetimes.
- [FilesNavigation.svelte](./FilesNavigation.svelte) — Consistent home and child path rows, known-ancestor overflow and confirmed mobile parent links.
- [files-navigation.test.ts](./files-navigation.test.ts) — Root, partial path, ancestor overflow, mobile parent markup and independent failure presentation tests.
- [NewFolderForm.svelte](./NewFolderForm.svelte) — Inline folder creation with optional description guidance.
