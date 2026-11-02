---
type: Software Module
title: "Files components"
description: "User filesystem browsing, accessible node sharing, folder creation and single-file uploads."
---

# Files

- [NodeActions.svelte](./NodeActions.svelte) — Files-owned icon-labelled action menus with row sharing, editing, moving and deletion, plus persistent dialogs.
- [NodeActionIcon.svelte](./NodeActionIcon.svelte) — Decorative icons for filesystem menu actions and recovery entries.
- [node-actions.dom.test.ts](./node-actions.dom.test.ts) — Single row trigger, icon-labelled actions, sharing eligibility and deletion lifecycle interactions.
- [node-actions-state.svelte.ts](./node-actions-state.svelte.ts) — Menu visibility, action dispatch and persistent-trigger focus restoration.
- [NodeDescriptionDialog.svelte](./NodeDescriptionDialog.svelte) — Native description editor with pending guards and explicit conflict recovery.
- [NodeUpdateDialog.svelte](./NodeUpdateDialog.svelte) — Feature-owned native rename and move dialogs with an independent directory picker and explicit reload recovery.
- [node-update.dom.test.ts](./node-update.dom.test.ts) — Selected actions, root hiding, rename collisions, directory selection and cancellation interactions.

- [files-components.test.ts](./files-components.test.ts) — Coherent browse loading, fail-closed heading and path rendering, navigation and creation form tests.
- [FilesDescription.svelte](./FilesDescription.svelte) — Read-only current file and folder descriptions, separate from contextual editing actions.
- [files-description.dom.test.ts](./files-description.dom.test.ts) — Description editing, clear, cancel, pending, denied, conflict and creation input interactions.
- [FilesContent.svelte](./FilesContent.svelte) — Compact table, pointer-following file previews, contextual actions and separate internal-move and external-upload drops.
- [row-presentation.ts](./row-presentation.ts) — Whitespace-normalized description previews capped at 120 characters without changing detail text.
- [row-presentation.test.ts](./row-presentation.test.ts) — Preview whitespace, character limits and Unicode truncation tests.
- [file-drag-move.dom.test.ts](./file-drag-move.dom.test.ts) — Drag preview identity and positioning, targeting, reconciliation, focus, recovery and external upload isolation.
- [FileUploadForm.svelte](./FileUploadForm.svelte) — Native upload modal, file picker, drop target and server-validated upload feedback.
- [file-upload-form.test.ts](./file-upload-form.test.ts) — Modal semantics, accessible selection, validation and pending states.
- [FileDeletionDialog.svelte](./FileDeletionDialog.svelte) — Files-owned permanent removal confirmation using shared native-dialog mechanics.
- [file-deletion.test.ts](./file-deletion.test.ts) — Row and details eligibility, accessible filename-specific confirmation and danger action presentation tests.
- [NodeShareButton.svelte](./NodeShareButton.svelte) — Filename-labelled, authority-confirmed sharing entrypoints with one decorative share icon.
- [NodeSharingDialog.svelte](./NodeSharingDialog.svelte) — Sharing modal with a searchable custom group picker and explicit permissions.
- [node-sharing.dom.test.ts](./node-sharing.dom.test.ts) — Searchable recipient selection, action visibility, draft editing, pending guards and focus recovery tests.
- [FilesPage.svelte](./FilesPage.svelte) — Files composition with independent neutral profile loading.
- [FilesNavigation.svelte](./FilesNavigation.svelte) — Compact breadcrumbs, known-ancestor overflow and confirmed mobile parent links.
- [files-navigation.test.ts](./files-navigation.test.ts) — Root, partial path, ancestor overflow, mobile parent markup and independent failure presentation tests.
- [NewFolderForm.svelte](./NewFolderForm.svelte) — Inline folder creation with optional description guidance.
