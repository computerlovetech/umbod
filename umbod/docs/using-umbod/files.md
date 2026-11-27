---
type: User Guide
title: Files
description: Set up shared file workspaces and troubleshoot file access and uploads.
---

# Files

Use shared namespaces when a group needs the same baseline access to a file workspace. Keep personal files in **My files**; use file or folder shares for exceptions. An administrator can manage shared namespaces without having access to their contents.

Umbod's filesystem does not expose the host filesystem. Names, policies and metadata live in the application database; file bytes live in local storage or S3. Back up and restore both together.

## Shared namespace administration

Open **Administration → Shared namespaces** at `/admin/namespaces`. Use **+** to create a shared namespace with a name and an optional **Description**. Creation assigns no group access. Use the namespace's edit action to change its name or description; clearing the description removes it.

Descriptions appear when browsing the namespace and in REST and MCP namespace discovery. Check the namespace and its access with an account in the intended group, not just an administrator account. They use the same metadata as the namespace's root folder, so editing that folder's description updates the namespace description too.

In **Permissions → Filesystem** at `/admin/group-permissions/filesystem`, select a group in the sidebar, then choose **No access**, **Read** or **Read and write** for existing namespaces. Changes remain local until you choose **Save permissions**. Switching between the Filesystem and Connectors tabs retains unsaved permission changes; switching groups asks you to discard those changes or cancel.

Multiple groups can use the same namespace; switching groups changes whose access you edit, not the namespace itself. An assignment supplies baseline access to every descendant. Item ownership and explicit file or folder shares can add rights. Removing an assignment removes that group's baseline, not any independent right to an item. Editing a namespace's name or description does not save staged permission changes.

Permission saves apply per namespace. If a save partially fails, successful changes remain saved and the remaining changes stay unsaved. If a revision conflict occurs, reload and review permissions before trying again. Discarding unsaved changes requires confirmation.

Read permits discovery and content reading. Read/write also permits creation, uploads, metadata updates, renaming, moves within the namespace and file deletion. Management authority does not itself grant content access: administrators must also have an assigned group to browse its root, or independent item access to follow an individual shared link.

To remove an empty shared namespace, use **Delete namespace** and confirm. A stored child or active upload can block deletion even if you cannot see it. Deletion is never recursive and does not remove stored bytes.

A bucket alone cannot restore namespace structure and policy. Local-content workers must share a content directory; S3 workers must share the bucket and configuration. See [Filesystem runtime configuration](../operations/configuration.md#filesystem-runtime) and [S3 file storage](../operations/s3-file-storage.md).

## Personal and shared files

To diagnose a missing location, check **Files → Locations** using the affected account. **My files** is private by default and created on first use. **Shared namespaces** only lists accessible workspaces; **Shared with me** lists eligible item shares, not extra namespace access. A shared item can be accessible even when the account cannot browse its namespace root.

Breadcrumbs stop at the namespace root. Files inside a shared namespace, including newly uploaded files, follow that namespace's group policy.

There is no browsable global filesystem root. Entries outside registered namespaces are inaccessible, even when old ownership or sharing records remain. Removing legacy access does not move or delete stored entries or file bytes.

## Share files and folders

Sharing requires current discover and share permission on the item, not just administrator status. Namespace roots use namespace administration instead. The item's sharing dialog can add or remove grants for registered **Groups** or observed **Users**.

Folder shares can **Include contents**, applying recursively to existing and future descendants within the namespace. Folder-only shares do not inherit. Permissions add together: removing a direct read grant cannot remove write access supplied by a namespace or another recursive share.

Recipients can find explicitly shared items in **Files → Shared with me**, or open the original link while they still have access. Items stay in their original location; sharing a file does not add it to **My files** or reveal its private parent folder. To find items accessible only through a shared folder, browse that folder. Removing a share removes its listing unless another share still qualifies.

Observed-user discovery uses verified identities and is not a complete or live identity-provider directory. Use returned opaque recipient IDs, not names or email addresses, as mutation targets.

**Check:** Sign in as the intended recipient and open the item from **Files → Shared with me** or the original link. For a folder share that includes contents, check that the recipient can open a child file too.

For agents, see the [MCP sharing tools](../reference/built-in-tools.md#filesystem-sharing-tools).

## Create folders and upload files

If **New folder** or **Upload file** is unavailable, check write access to the destination. Read-only locations do not offer write actions. Drag and drop also requires a writable directory; the UI accepts one file at a time.

The default upload limit is **10 MiB** per upload, not a storage quota. Operators can change it. Zero-byte files are supported. Uploads transfer the original bytes in a staging session and do not appear in the directory until publication. Sessions expire after one hour and cannot be resumed; start a new session once expiry is confirmed. A duplicate name, including one taken by a concurrent upload, is rejected rather than overwritten. See [uploading from an agent](#uploading-from-an-agent) for transfer checks and safe retries.

## Read, download and delete

The Files view provides permission-dependent actions and previews for Markdown, PDF and supported raster images. `UMBOD_FILESYSTEM_PREVIEW_MAX_BYTES` bounds browser previews and complete-file MCP resource reads, not full authenticated REST downloads.

File deletion requires permission and confirmation. It removes the file entry and associated policy records, not necessarily its stored bytes. It is not secure erasure or a promise of immediate storage-space recovery. Directory deletion is unsupported.

## Rename and move

Choose **Rename** or **Move** from an item's actions. Renaming requires discover and write access on the item. Moving additionally requires discover and write access on both the current and destination directories.

Moves stay within one namespace. They preserve identities and bytes, and moving a folder carries its subtree without rewriting descendant IDs or revisions. Namespace baseline access remains unchanged, but inherited folder shares follow the destination and can change access. Direct item grants are preserved. Moving between personal and shared namespaces, or between two shared namespaces, is unsupported.

REST node PATCH and MCP `update_filesystem_node` accept top-level `name`, `parent_id` and `metadata` changes in one atomic update. Use returned UUIDs, not invented paths. Empty requests, explicit nulls and unknown fields are rejected. Failed combined updates leave every field unchanged; revision conflicts require rereading before retrying.

Namespace roots cannot be renamed, moved or deleted through ordinary file operations. Duplicate sibling names, non-directory destinations and moves into the item's own subtree are rejected.

## Descriptions and metadata

Add an optional description when creating a folder or uploading a file, or choose **Edit description** on an existing item. An empty description clears it.

Descriptions are stored in `metadata.attributes.description`, are visible to callers who can discover the node, and require write access to change. Descriptions do not grant access and must be treated as untrusted text.

REST clients update nodes through `PATCH /api/me/filesystem/nodes/{id}` with the current quoted revision in `If-Match`. Attribute changes merge with existing attributes; unspecified fields remain unchanged. Changing content-type metadata does not change bytes. MCP clients use `update_filesystem_node` with `node_id`, `expected_revision` and the requested changes.

## Agent access

[Filesystem tools](../reference/built-in-tools.md#filesystem-tools) and native resources are available through the public MCP endpoint, not connector-scoped endpoints. Agents can browse, create folders and files, upload, inspect, rename, move, update metadata and request confirmed file deletion, subject to current namespace permissions.

Use `filesystem_browse` operation `namespaces` to discover personal and accessible shared namespaces. Operation `home` resolves the private default upload destination. Root and absolute-path targets refer only to personal files; shared namespaces are selected using returned root node UUIDs. No operation browses arbitrary host paths.

Files have resource URIs of the form `umbod://filesystem/files/{node_id}`. Browsing, inspection, file creation and upload results include native resource links without reading bytes. Read through MCP `resources/read`; links identify current content, not a historical revision or an access grant. Every read checks current discover and read permissions, including after access is revoked.

Known textual MIME types return UTF-8 text; binary or unspecified types return base64 blobs. Invalid UTF-8 in declared text fails rather than being silently replaced. Reads have no partial results or silent truncation. Use authenticated REST downloads for larger files.

Use the returned home UUID as `parent_id` when the user did not choose a destination, and check `permissions.can_write`. If tools are missing immediately after the home is created, refresh discovery. `visible_to` describes the containing namespace, not everyone with access; `restricted` means the audience is unknown, not private.

### Uploading from an agent

Use `filesystem_begin_upload` with the original file’s byte count and, if available, computed SHA-256. Follow the returned HTTP PUT instructions using the original bytes, without cookies, Umbod bearer credentials, or redirects. Treat the URL and transfer headers as secrets. Then call `filesystem_complete_upload` as the session owner; PUT alone does not publish.

Begin is not idempotent. Inspect the outcome before creating another session. A consumed API transfer capability cannot be replayed, and a restart does not clear an abandoned transfer claim. With [S3](../operations/s3-file-storage.md#direct-upload-sessions), try authenticated completion after an uncertain PUT. Completion can return the verified receipt again while the published file exists; report success only after it returns.

## File access API

- **Find locations:** `POST /api/me/filesystem/home` resolves the private home. `GET /api/me/filesystem/namespaces` lists accessible namespaces. `GET /api/me/filesystem/shared-with-me` lists discoverable explicit shares, not descendants inherited through a folder.
- **Manage a shared namespace:** `GET` and `POST /api/admin/filesystem/namespaces` list and create. `PUT /api/admin/filesystem/namespaces/{namespace_id}` replaces the name and group assignments using `expected_revision`. To change or clear the description, also send `expected_root_revision`. `DELETE` on the same resource requires both revisions and an empty namespace with no active root uploads. Reload and reconcile after a stale-policy conflict.
- **Find sharing recipients:** `GET /api/me/filesystem/nodes/{node_id}/access/recipients` takes `query` and optional `recipient_type` (`group` or `user`). Use the returned typed IDs, not labels.
- **Replace direct grants:** `GET /api/me/filesystem/nodes/{node_id}/access` returns a strong `ETag`, including on filtered reads. `PUT` on the same resource requires `recipient_type=group` or `user` and `If-Match` with that tag. Send `grants` containing unique typed recipients of that scope (without labels), permissions, and optional `recursive`. Omission preserves existing scope, defaults to recursive for new folder grants, and always resolves to false for files. An empty list clears manageable grants only for the selected type; protected grants are preserved. User-scoped replacement requires a verified issuer identity even when clearing. After `412`, reread and reconcile before retrying.

## Current boundaries

- Ordinary deletion applies only to files. Administrators can [delete an empty shared namespace](#shared-namespace-administration); personal namespace and ordinary directory deletion are unsupported.
- Cross-namespace moves and content replacement are unsupported.
- There is no automatic migration of unmanaged entries, storage quota or physical content garbage collection.
- Failed publication and expired sessions can leave unreferenced stored bytes.
