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

A new file is private to its creator. Directory sharing does not automatically share new files or subfolders. Duplicate names are rejected rather than overwritten; an upload can fail at completion if another file has taken the same name. Zero-byte files are allowed.

The default maximum upload is **10 MiB**, configurable by the operator. An upload session expires after one hour; it is not a resumable upload. A configured byte limit is a per-upload limit, not a user storage quota.

### Share with a group

For nodes you may share, open the sharing dialog, search registered groups, choose permissions, and save. Remove a group's grant through the same dialog when access is no longer needed.

| Permission | Purpose |
| --- | --- |
| `discover` | Visibility of the node when browsing |
| `read` | Read access to the node and file content |
| `write` | Write operations, including creating children in a directory |
| `delete` | Delete a file; directories and root cannot currently be deleted |
| `share` | Manage access grants |

Permissions apply directly to the selected node. They do not inherit from a parent folder. A share on a folder is therefore not a recursive share of its contents. Owners have authority over their nodes; other users need matching grants. Sharing requires current `discover` and `share` authority on that node. For normal file reading, grant both `discover` and `read`; `read` alone does not make a file visible.

### Share with an observed user

MCP tools and REST clients can also grant access directly to a user. The browser sharing dialog currently manages groups only. Find an eligible recipient with `filesystem_search_sharing_recipients`, then pass its opaque `user_id` to `filesystem_share`; see the [filesystem sharing reference](../reference/filesystem-sharing.md) for request fields and REST replacement rules.

Umbod's user directory records users observed during verified authentication. It is not a complete or live identity-provider directory, and an observed record does not prove an account is still active. Search matches user names, not email addresses or authentication subjects. Users without names are not searchable; identical names can identify different users. Always use the returned opaque ID rather than inventing one from a name or email.

A recipient can access a directly shared file by its node ID without access to the parent directory. Sharing does not send notifications or provide a dedicated shared-files listing. Communicate the node ID or MCP resource URI separately when the recipient cannot find it by browsing.

Sharing summaries describe manageable direct grants, not every source of effective access. An empty summary is not proof that nobody else has access. Protected grants, including recursive, unresolved, malformed, and foreign-issuer grants, are not rewritten by the sharing editor.

### Read and delete

The current Files view provides file metadata and permission-dependent actions, but does not yet provide a download/open-content control. Authenticated clients can download through the REST node-content endpoint; agents can read supported files through native MCP resources.

Deletion requires permission and confirmation. It removes the file's namespace entry and access policy; it does not currently guarantee physical removal of the stored bytes. Do not treat deletion as secure erasure or immediate recovery of storage space.

## Agent access

Filesystem tools and resources are available through Umbod's root MCP endpoint, not connector-scoped endpoints. Tools support browsing, inspecting nodes, uploading, deleting files, and direct group/user sharing. Native MCP resources provide complete-file reads, subject to the caller's filesystem permissions.

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
- Rename, move, content replacement, and dedicated owned/shared listings are not implemented; planned REST operations return `501`.
- There is no automatic storage migration, storage quota/accounting, or physical content garbage collection.
- Failed publication can leave unreferenced content. Expired sessions do not imply automatic cleanup of their stored bytes.
- The UI, REST clients, and MCP tools share filesystem authorization, but do not yet expose identical controls.
