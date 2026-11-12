---
type: Software Module
title: "Files components"
description: "User filesystem browsing, accessible node sharing, folder creation and single-file uploads."
---

# Files

- [preview/README.md](./preview/README.md) — Filetype-adapted content previews, initially safe Markdown, with loading and recovery presentation.

- [NodeActions.svelte](./NodeActions.svelte) — Files-owned detail, sharing and mutation menus with authoritative live-node dialogs and persistent focus restoration.
- [NodeDetailsDialog.svelte](./NodeDetailsDialog.svelte) — Feature-owned read-only node metadata and the caller’s five explicit permissions, without ownership or grant policy.
- [PermissionBadge.svelte](./PermissionBadge.svelte) — Neutral permissions-only badge shared by current-node titles and row names.
- [permission-label.ts](./permission-label.ts) — Exact caller permission combinations summarized without implying unsupported operations.
- [permission-label.test.ts](./permission-label.test.ts) — Read-only, editable, discover-only and custom permission label cases.
- [node-details.dom.test.ts](./node-details.dom.test.ts) — Details eligibility, fields, live updates, access loss, navigation cleanup, personal root protection and focus restoration.
- [node-details-inputs.svelte.test-support.ts](./node-details-inputs.svelte.test-support.ts) — Reactive live node inputs for isolated details interaction tests.
- [NodeActionIcon.svelte](./NodeActionIcon.svelte) — Decorative icons for filesystem menu actions and recovery entries.
- [node-actions.dom.test.ts](./node-actions.dom.test.ts) — Single row trigger, icon-labelled actions, sharing eligibility and deletion lifecycle interactions.
- [node-actions-state.test.ts](./node-actions-state.test.ts) — Discover-only eligibility, live authoritative node reads, menu dismissal and explicit details closure.
- [node-actions-state.svelte.ts](./node-actions-state.svelte.ts) — Live details selection, menu eligibility, action dispatch and persistent-trigger focus restoration.
- [NodeDescriptionDialog.svelte](./NodeDescriptionDialog.svelte) — Native description editor with pending guards and explicit conflict recovery.
- [NodeUpdateDialog.svelte](./NodeUpdateDialog.svelte) — Files-owned rename and picker/native move reviews with inherited-access warnings and explicit confirmation.
- [node-update.dom.test.ts](./node-update.dom.test.ts) — Rename, destination selection, branch retries, cancellation and empty-folder keyboard focus interactions.
- [folder-picker-focus-state.svelte.ts](./folder-picker-focus-state.svelte.ts) — Keeps focused folder disclosures mounted until blur when asynchronous loading reveals an empty branch.

- [files-components.test.ts](./files-components.test.ts) — Coherent browse loading, fail-closed heading and path rendering, navigation and creation form tests.
- [FilesDescription.svelte](./FilesDescription.svelte) — Read-only current file and folder descriptions, separate from contextual editing actions.
- [files-description.dom.test.ts](./files-description.dom.test.ts) — Description editing, clear, cancel, pending, denied, conflict and creation input interactions.
- [FilesContainer.svelte](./FilesContainer.svelte) — Shared home, folder and file layout with stable heading height, navigation, actions and description slots.
- [FilesContent.svelte](./FilesContent.svelte) — File and folder composition with common actions and descriptions, compact listings, metadata, drag previews and upload drops.
- [FileTypeIcon.svelte](./FileTypeIcon.svelte) — Accessible format, folder and explicit home icons shared by list rows and filename-based drag previews.
- [file-type-icons.ts](./file-type-icons.ts) — Common format groups and explicit home SVGs; specific MIME types precede extensions, with safe generic and text fallbacks.
- [file-type-icons.test.ts](./file-type-icons.test.ts) — Grouped extensions, MIME precedence, normalization, unknown formats and directory overrides.
- [file-type-icon.dom.test.ts](./file-type-icon.dom.test.ts) — Accessible category rendering and in-place row icon changes after a filename extension is renamed.
- [file-drag-move.dom.test.ts](./file-drag-move.dom.test.ts) — Drag previews, move review confirmation/cancellation, reconciliation, focus, recovery and external upload isolation.
- [FileUploadForm.svelte](./FileUploadForm.svelte) — Native upload modal, file picker, drop target and server-validated upload feedback.
- [file-upload-form.test.ts](./file-upload-form.test.ts) — Modal semantics, accessible selection, validation and pending states.
- [FileDeletionDialog.svelte](./FileDeletionDialog.svelte) — Files-owned permanent removal confirmation using shared native-dialog mechanics.
- [file-deletion.test.ts](./file-deletion.test.ts) — Row and details eligibility, accessible filename-specific confirmation and danger action presentation tests.
- [NodeShareButton.svelte](./NodeShareButton.svelte) — Filename-labelled, authority-confirmed sharing entrypoints with one decorative share icon.
- [NodeSharingDialog.svelte](./NodeSharingDialog.svelte) — Sharing modal with recipient search, explicit permissions, Include contents scope and widening warnings.
- [node-sharing.dom.test.ts](./node-sharing.dom.test.ts) — Searchable recipient selection, action visibility, draft editing, pending guards and focus recovery tests.
- [FilesPage.svelte](./FilesPage.svelte) — Files composition with independent neutral profile loading.
- [FilesNavigation.svelte](./FilesNavigation.svelte) — Consistent home and child path rows, known-ancestor overflow and confirmed mobile parent links.
- [files-navigation.test.ts](./files-navigation.test.ts) — Root, partial path, ancestor overflow, mobile parent markup and independent failure presentation tests.
- [NewFolderForm.svelte](./NewFolderForm.svelte) — Inline folder creation with optional description guidance.
