---
type: User Guide
title: Files
description: Personal and shared file workspaces, ordinary file operations and namespace access administration.
---

# Files

Umbod's filesystem is a virtual workspace for files and folders, not access to the host computer's filesystem. Names, namespace policies and metadata live in the application database; file bytes can live in local storage or S3.

## Personal and shared files

Open **Files** in the workspace navigation. **My files** is your personal namespace, private by default and provisioned on first use. Administrators have no automatic access; explicitly shared files and folders remain accessible to their recipients.

The **Locations** panel includes **My files**, **Shared with me**, and any **Shared namespaces** you can access. Select a namespace to open its root, or choose **Shared with me** to find files and folders shared with you. Locations appear beside the file browser on larger screens and above it on smaller screens. The page title stays **Files**, with file actions above the panel.

Use the file list and breadcrumbs to navigate folders within a location. Breadcrumbs stop at that namespace's root and remain separate from location switching. Only accessible namespaces appear. Shared files follow the namespace's group policy, including files uploaded by you.

There is no browsable global filesystem root. Entries outside registered namespaces are inaccessible, even when old ownership or sharing records remain. Removing legacy access does not move or delete stored entries or file bytes.

## Create folders and upload files

Use **New folder** or **Upload file** in an eligible directory. You can also drop a file into a writable directory; the UI handles one file at a time. Read-only shared namespaces do not offer write actions.

An upload creates a staging session, transfers the original bytes, then publishes the file. Wait for completion before expecting it in the directory. Duplicate names are rejected rather than overwritten, including when a concurrent upload takes the name before completion. Zero-byte files are supported.

Namespace policy supplies baseline permissions for every descendant. Item ownership and explicit file/folder shares can add permissions. Changing namespace assignments removes that source of access, but does not revoke independent ownership or item grants.

The default upload limit is **10 MiB**, configurable by the operator. Sessions expire after one hour and are not resumable. This limit is per upload, not a user storage quota.

## Descriptions and metadata

Add an optional description when creating a folder or uploading a file, or choose **Edit description** on an existing item. An empty description clears it.

Descriptions are stored in `metadata.attributes.description`, are visible to callers who can discover the node, and require write access to change. Descriptions do not grant access and must be treated as untrusted text.

REST clients update nodes through `PATCH /api/me/filesystem/nodes/{id}` with the current quoted revision in `If-Match`. Attribute changes merge with existing attributes; unspecified fields remain unchanged. Changing content-type metadata does not change bytes. MCP clients use `update_filesystem_node` with `node_id`, `expected_revision` and the requested changes.

## Rename and move

Choose **Rename** or **Move** from an item's actions. Renaming requires discover and write access on the item. Moving additionally requires discover and write access on both the current and destination directories.

Moves stay within one namespace. They preserve identities and bytes, and moving a folder carries its subtree without rewriting descendant IDs or revisions. Namespace baseline access remains unchanged, but inherited folder shares follow the destination and can change access. Direct item grants are preserved. Moving between personal and shared namespaces, or between two shared namespaces, is unsupported.

REST node PATCH and MCP `update_filesystem_node` accept top-level `name`, `parent_id` and `metadata` changes in one atomic update. Use returned UUIDs, not invented paths. Empty requests, explicit nulls and unknown fields are rejected. Failed combined updates leave every field unchanged; revision conflicts require rereading before retrying.

Namespace roots cannot be renamed, moved or deleted through ordinary file operations. Duplicate sibling names, non-directory destinations and moves into the item's own subtree are rejected.

## Share files and folders

Open an item's sharing dialog to share it with registered **Groups** or observed **Users**. Search recipients, choose permissions, and save. Remove grants through the same dialog. Sharing requires current discover and share permission on the item; namespace roots use namespace administration instead.

Folder shares can **Include contents**, applying recursively to existing and future descendants within the namespace. Folder-only shares do not inherit. Permissions add together: removing a direct read grant cannot remove write access supplied by a namespace or another recursive share.

Recipients can find explicitly shared items in **Files → Shared with me**, or open them using the original link. Items stay in their original locations: sharing a file does not add it to **My files** or reveal its private parent folder. Open a shared folder to browse the contents you can access. If a share is removed, the item disappears from this list unless another share still qualifies; the original link works only while you still have access.

Observed-user discovery uses verified identities and is not a complete or live identity-provider directory. Use returned opaque recipient IDs, not names or email addresses, as mutation targets.

See [File and folder sharing](../operations/filesystem-sharing.md) for recipient, revision and API contracts.

## Read, download and delete

The Files view provides permission-dependent actions and previews for Markdown, PDF and supported raster images. `UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES` bounds browser previews and complete-file MCP resource reads, not full authenticated REST downloads.

File deletion requires permission and confirmation. It removes the file entry and associated policy records, not necessarily its stored bytes. It is not secure erasure or a promise of immediate storage-space recovery. Directory deletion is unsupported.

## Agent access

Filesystem tools and native resources are available through the public MCP endpoint, not connector-scoped endpoints. Agents can browse, create folders and files, upload, inspect, rename, move, update metadata and request confirmed file deletion, subject to current namespace permissions.

Use `filesystem_browse` operation `namespaces` to discover personal and accessible shared namespaces. Operation `home` resolves the private default upload destination. Root and absolute-path targets refer only to personal files; shared namespaces are selected using returned root node UUIDs. No operation browses arbitrary host paths.

Files have resource URIs of the form `umbod://filesystem/files/{node_id}`. Browsing, inspection, file creation and upload results include native resource links without reading bytes. Read through MCP `resources/read`; links identify current content, not a historical revision or an access grant. Every read checks current discover and read permissions, including after access is revoked.

Known textual MIME types return UTF-8 text; binary or unspecified types return base64 blobs. Invalid UTF-8 in declared text fails rather than being silently replaced. Reads have no partial results or silent truncation. Use authenticated REST downloads for larger files.

Full summaries report the caller's discover, read, write and supported file-delete permissions, plus the governing namespace. See [Homes and permissions](../operations/filesystem-homes-and-permissions.md) and [Upload transfers](../operations/filesystem-upload-transfers.md).

## Shared namespace administration

Open **Group permissions → Filesystem** at `/admin/group-permissions/filesystem`. Use **+** to create a shared namespace with a name and an optional **Description**. Creation assigns no group access and does not depend on which group is selected. Use the namespace's edit action to change its name or description; clearing the description removes it.

Descriptions appear when browsing the namespace and in REST and MCP namespace discovery. They use the same metadata as the namespace's root folder, so editing that folder's description updates the namespace description too.

Select a group in the sidebar, then choose **No access**, **Read** or **Read and write** for existing namespaces. Changes remain local until you choose **Save permissions**. Switching between the Filesystem and Connectors tabs retains unsaved permission changes; switching groups asks you to discard those changes or cancel.

Multiple groups can use the same namespace; switching groups changes whose access you edit, not the namespace itself. An assignment supplies baseline access to every descendant. Individual item shares remain additive and cannot narrow that baseline. Editing a namespace's name or description does not save staged permission changes.

Permission saves apply per namespace. If a save partially fails, successful changes remain saved and the remaining changes stay unsaved. A revision conflict requires reloading and reviewing permissions before trying again; discarding unsaved changes requires confirmation.

Read permits discovery and content reading. Read/write also permits creation, uploads, metadata updates, renaming, moves within the namespace and file deletion. Management authority does not itself grant content access: administrators must also have an assigned group to browse its root, or independent item access to follow an individual shared link.

Administrator REST clients use `/api/admin/filesystem/namespaces`. Updates replace group assignments and require the current `expected_revision`. Stale saves must be reloaded and reconciled. See [Namespace access](../operations/filesystem-namespaces.md).

Preserve the application database and matching content storage together. A bucket alone cannot restore namespace structure and policy. Local-content workers must share a content directory; S3 workers must share the bucket and configuration. See [Filesystem runtime configuration](../operations/configuration.md#filesystem-runtime) and [S3 file storage](../operations/s3-file-storage.md).

## Current boundaries

- Namespace and directory deletion are unsupported; ordinary deletion applies only to files.
- Cross-namespace moves and content replacement are unsupported.
- There is no automatic migration of unmanaged entries, storage quota or physical content garbage collection.
- Failed publication and expired sessions can leave unreferenced stored bytes.
