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

Permissions apply directly to the selected node. They do not inherit from a parent folder. A share on a folder is therefore not a recursive share of its contents. Owners have authority over their nodes; other users need matching grants.

### Read and delete

The current Files view provides file metadata and permission-dependent actions, but does not yet provide a download/open-content control. Authenticated clients can download through the REST node-content endpoint; agents can read supported files through filesystem tools.

Deletion requires permission and confirmation. It removes the file's namespace entry and access policy; it does not currently guarantee physical removal of the stored bytes. Do not treat deletion as secure erasure or immediate recovery of storage space.

## Agent access

Filesystem tools are available through Umbod's root MCP endpoint, not connector-scoped endpoints. They support browsing, inspecting nodes, uploading, reading complete files, deleting files, and group sharing, subject to the caller's filesystem permissions.

Connecting an agent does not grant it unrestricted file access. Tool operations use Umbod's virtual filesystem and check authorization; they do not browse arbitrary host paths or bootstrap root permissions.

MCP uploads have a maximum of 10 MiB, or the configured filesystem limit if lower. Complete-file MCP reads are limited to 1 MiB. These tool limits are separate from browser/API upload and proxy limits.

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
