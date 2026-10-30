---
type: Software Module
title: "Files components"
description: "User filesystem browsing, accessible node sharing, folder creation and single-file uploads."
---

# Files

- [files-components.test.ts](./files-components.test.ts) — Navigation and form presentation tests.
- [FilesContent.svelte](./FilesContent.svelte) — Full-row file and folder links, hover and focus highlights, separate deletion actions, metadata and upload drop overlay.
- [FileUploadForm.svelte](./FileUploadForm.svelte) — Native upload modal, file picker, drop target and server-validated upload feedback.
- [file-upload-form.test.ts](./file-upload-form.test.ts) — Modal semantics, accessible selection, validation and pending states.
- [FileDeletionDialog.svelte](./FileDeletionDialog.svelte) — Files-owned permanent removal confirmation using shared native-dialog mechanics.
- [file-deletion.test.ts](./file-deletion.test.ts) — Row and details eligibility, accessible filename-specific confirmation and danger action presentation tests.
- [NodeShareButton.svelte](./NodeShareButton.svelte) — Filename-labelled, authority-confirmed sharing entrypoints with one decorative share icon.
- [NodeSharingDialog.svelte](./NodeSharingDialog.svelte) — Sharing modal with a searchable custom group picker and explicit permissions.
- [node-sharing.dom.test.ts](./node-sharing.dom.test.ts) — Searchable recipient selection, action visibility, draft editing, pending guards and focus recovery tests.
- [FilesPage.svelte](./FilesPage.svelte) — Files page composition.
- [FilesNavigation.svelte](./FilesNavigation.svelte) — Compact breadcrumbs, known-ancestor overflow and confirmed mobile parent links.
- [files-navigation.test.ts](./files-navigation.test.ts) — Root, partial path, ancestor overflow, mobile parent markup and independent failure presentation tests.
- [NewFolderForm.svelte](./NewFolderForm.svelte) — Inline folder creation form.
