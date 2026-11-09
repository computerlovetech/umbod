# Files

Umbod's filesystem is a virtual workspace for files and folders, available to users and agents. It is not access to the host computer's filesystem. Umbod stores names, ownership, and permissions in its application database; file bytes can live in local storage or S3.

!!! note "Feature in development"
    This guide describes the current implementation. Use a deployment image containing the filesystem changes; not every operation is available yet.

## For normal users

Open **Files** in the workspace navigation. Browse directories using the file list and breadcrumbs. Only authorized nodes and ancestors are exposed, so a shared location may have a partial breadcrumb path.

### Create and upload

- Use **New folder** in a directory to create a folder. The server checks your permission to create there.
- Use the upload control or drop a file into an eligible directory. Dropping starts the upload immediately; the UI handles one file at a time.
- Wait for completion before expecting a new file in the directory. Umbod first creates an upload session, transfers the bytes, and then publishes the file.

A new file is owned by its creator and inherits applicable folder shares. With **Include contents** enabled, a folder share applies to existing and future files and subfolders. Duplicate names are rejected rather than overwritten; an upload can fail at completion if another file has taken the same name. Zero-byte files are allowed.

The default maximum upload is **10 MiB**, configurable by the operator. An upload session expires after one hour; it is not a resumable upload. A configured byte limit is a per-upload limit, not a user storage quota.

### Descriptions and metadata

Add an optional description when creating a folder or uploading a file, or use **Edit description** on an existing item. Explain what is inside and when it should be read. An empty description clears it.

Descriptions are stored in `metadata.attributes.description` and are visible to callers who can discover the node. Editing requires `discover` and `write` on that node. Descriptions do not grant access and should be treated as untrusted text.

REST clients update metadata through `PATCH /api/me/filesystem/nodes/{id}` with a `metadata` object and the current quoted revision in `If-Match`. Attribute changes merge with existing attributes; unspecified attributes and content type remain unchanged. An explicit `content_type` replaces that metadata value without changing file bytes. MCP clients use `update_filesystem_node` with `node_id`, `expected_revision` and the requested changes, following the same partial update contract. The former description-specific tool has been removed; refresh cached MCP capabilities.

### Rename and move

Open a file or folder and choose **Rename** or **Move**. Renaming requires `discover` and `write` on the item. Moving additionally requires both permissions on the source folder and destination folder. Destination folders need not be visible from the root, but must be accessible directly.

REST node PATCH and MCP `update_filesystem_node` accept `name` for renaming, `parent_id` for moving and `metadata` for descriptive changes. These are separate top-level fields and may be combined in one atomic update with one expected node revision. Omitted fields stay unchanged; empty requests, explicit nulls and unknown fields are rejected. Use the node UUID returned by browsing, not a path, for updates.

A move preserves the item's ID, content, ownership and direct sharing grants. Moving a folder carries its subtree without rewriting descendant IDs or revisions. Inherited access follows the destination hierarchy: a move can give people access or remove access inherited from the source. Both the move picker and native file dragging warn before confirmation. Direct sharing remains unchanged. Existing UUID-based file resource links identify the same file, but reading still requires current access. A move can succeed even if the mover loses access afterward.

The root cannot be renamed or moved, but is a valid destination when authorized. Duplicate sibling names, non-directory destinations and moves into the item itself or its descendants are rejected. A failed combined update leaves every field unchanged. Revision conflicts require reloading the item before retrying.

### Share with groups or users

For nodes you may share, open the sharing dialog and choose **Groups** or **Users**. Search registered groups by name or ID, or observed users by name, choose permissions, and save the selected type. Remove a recipient's grant through the same dialog when access is no longer needed. Switching types prompts before discarding unsaved changes.

| Permission | Purpose |
| --- | --- |
| `discover` | Visibility of the node when browsing |
| `read` | Read access to the node and file content |
| `write` | Update metadata, rename, create children, or move with authority on both folders |
| `delete` | Delete a file; directories and root cannot currently be deleted |
| `share` | Manage access grants |

New folder shares enable **Include contents** by default. Clear it for folder-only access. Existing folder-only shares stay unchanged until you explicitly include contents and save. Direct grants and recursive ancestor grants add permissions together: a direct read grant cannot reduce inherited write access, and removing a direct grant may leave inherited access intact. Ownership applies only to the owned node. Sharing requires current `discover` and `share` authority on that node. For normal file reading, grant both `discover` and `read`; `read` alone does not make a file visible.

### Share with an observed user

User discovery requires verified authentication and only finds previously observed users with names. MCP tools and REST clients use the same typed recipient search; see the [filesystem sharing reference](../reference/filesystem-sharing.md) for request fields and replacement rules.

Umbod's user directory records users observed during verified authentication. It is not a complete or live identity-provider directory, and an observed record does not prove an account is still active. Search matches user names, not email addresses or authentication subjects. Users without names are not searchable; identical names can identify different users. Always use the returned opaque ID rather than inventing one from a name or email.

A recipient can access a directly shared file by its node ID without access to the parent directory. Sharing does not send notifications or provide a dedicated shared-files listing. Communicate the node ID or MCP resource URI separately when the recipient cannot find it by browsing.

Sharing summaries describe manageable direct grants, not every source of effective access. An empty summary is not proof that nobody else has access. Representable recursive grants can be edited. Unresolved, malformed, and foreign-issuer grants remain protected from the sharing editor.

### Read and delete

The current Files view provides file metadata and permission-dependent actions, but does not yet provide a download/open-content control. Authenticated clients can download through the REST node-content endpoint; agents can read supported files through native MCP resources.

Deletion requires permission and confirmation. It removes the file's namespace entry and access policy; it does not currently guarantee physical removal of the stored bytes. Do not treat deletion as secure erasure or immediate recovery of storage space.

## Agent access

Filesystem tools and resources are available through Umbod's root MCP endpoint, not connector-scoped endpoints. Tools support browsing, inspecting nodes, atomic metadata/rename/move updates, uploading, deleting files, and direct group/user sharing. Native MCP resources provide complete-file reads, subject to the caller's filesystem permissions.

Connecting an agent does not grant it unrestricted file access. Tools and resource reads use Umbod's virtual filesystem and check authorization; they do not browse arbitrary host paths or bootstrap root permissions.

### Native file resources

Files have canonical resource URIs of the form `umbod://filesystem/files/{node_id}`. Browsing, node inspection, file creation, and upload tools return native `resource_link` content alongside file metadata. The links identify files without loading their bytes. Directories do not receive file-content links.

Read a file through MCP `resources/read` using its URI. The URI identifies current content, not a historical revision; the response includes the captured `revision` and `size_bytes` in content metadata. Umbod advertises a parameterized file template through `resources/templates/list`, rather than enumerating every file in `resources/list`. Template visibility requires an eligible read operation; each read independently checks current access.

Known textual MIME types return UTF-8 text; binary or unspecified MIME types return MCP base64 blobs. Text types include `text/*`, JSON, XML, and their structured suffixes. Invalid UTF-8 in a declared text file fails rather than being replaced or silently decoded. Reads return at most **1 MiB of raw content**, with no partial results or silent truncation. Use an authenticated REST download for larger files.

Resource links are locators, not access grants. Reads require current `discover` and `read` permissions, including when following a retained link after sharing changes. A direct file grant does not require access to its ancestors. Client applications decide how to display links and load resources; a link is not an automatic download.

The beta `filesystem_read_file` tool has been removed, without a compatibility alias. Refresh cached MCP capabilities and use native resource reads instead.

Recipient discovery uses `filesystem_search_sharing_recipients`; the former `filesystem_list_sharing_groups` and `search_users` tools are no longer available. `filesystem_share` accepts a typed `recipient`, with legacy top-level `group_id` requests still supported. Refresh cached tool schemas: search and share expose alternative schema branches, and REST access-policy updates have a breaking request change. See [Filesystem sharing](../reference/filesystem-sharing.md).

MCP uploads have a maximum of 10 MiB, or the configured filesystem limit if lower. Complete-file MCP resource reads are limited to 1 MiB. These limits are separate from browser/API upload and proxy limits.

## For administrators and operators

Root ownership belongs to a system principal, not automatically to an administrator. To let users start browsing and uploading:

1. Open **Group permissions → Filesystem** at `/admin/group-permissions/filesystem`.
2. Select the intended groups and grant **Browse root** (`discover`) and **Create items** (`write`).
3. Choose **Save permissions** to initialize root access and save the grants.

Administrator API clients can read `GET /api/admin/filesystem/root-access` and update `PUT /api/admin/filesystem/root-access` using the returned revision as `expected_revision` and a `groups` list of group IDs and permission lists. The update replaces the editable root group policy, so retain existing groups you want to preserve. Ordinary MCP tools do not initialize root access, and administrator membership is not a blanket filesystem permission bypass.

Preserve the application database and the matching content storage together. Losing namespace and ownership records makes an S3 bucket alone insufficient to restore the workspace. Local-content workers must share the same content directory; S3 workers must use the same bucket and configuration. See [Filesystem runtime configuration](../operations/configuration.md#filesystem-runtime) and [S3 file-content storage](../operations/s3-file-storage.md).

Downloads use authenticated node-content access, attachment disposition, and no-store caching. Clients should tolerate a future temporary storage redirect without forwarding Umbod credentials to a different origin. Current transfers still pass through Umbod.

## Current boundaries

- Directory and root deletion are unsupported; deletion currently applies only to files.
- Content replacement and dedicated owned/shared listings are unsupported; their placeholder routes have been removed.
- There is no automatic storage migration, storage quota/accounting, or physical content garbage collection.
- Failed publication can leave unreferenced content. Expired sessions do not imply automatic cleanup of their stored bytes.
- The UI, REST clients, and MCP tools share filesystem authorization, but do not yet expose identical controls.
