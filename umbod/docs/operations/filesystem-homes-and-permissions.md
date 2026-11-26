---
type: Reference
title: Filesystem homes and permissions
description: Private upload destinations, namespace-owned caller permissions and safe visibility metadata.
---

# Filesystem homes and permissions

Keep uploads in the caller's personal namespace unless a destination was chosen. Before troubleshooting an upload or a missing file, check the caller's current access to the actual node. Administrator status is not content access, and visibility metadata is not a list of recipients.

## Choosing an upload destination

When no destination is specified, use the targetless `home` operation of `filesystem_browse`. It resolves or provisions the caller's private personal namespace and returns its home node and namespace-bounded breadcrumbs. Use the returned UUID as the upload's `parent_id`.

The targetless `namespaces` operation lists this personal namespace and accessible shared namespaces. Root and absolute-path browse targets resolve only within personal files. Select a shared namespace using its returned `root_node_id`; do not infer a path from its display name.

If upload tools do not appear immediately after first use, refresh tool discovery. First use records the new home durably; the delay in updating tool discovery does not invalidate returned permissions. REST exposes home resolution through `POST /api/me/filesystem/home` and discovery through `GET /api/me/filesystem/namespaces`.

Check `permissions.can_write`, not a folder name, administrator role or creator identity. The result reports permissions at that moment; each later operation checks access again. An update response reports access as of the transaction. Do not retry a committed update just because the caller can no longer discover the item afterward.

For an existing local file, compute its exact byte count and preferably its SHA-256 from the original bytes. Use `filesystem_begin_upload`, transfer those bytes using its HTTP instructions, then call `filesystem_complete_upload`. Do not reconstruct local contents as generated text or invent a checksum. See [Upload transfers](filesystem-upload-transfers.md).

Report success only after completion, using the returned identity, verified size and SHA-256, and current `visible_to` descriptor. On a completion retry, the receipt still describes the verified bytes, but access is checked again. Report restricted visibility as unknown, not private.

## Personal namespace identity

Home identity is bound to the exact trusted issuer and user identifier. A durable binding, not a name or path, identifies it. Repeated and concurrent requests resolve the same directory. Lookup never adopts an arbitrary folder because its name resembles a home; inconsistent bindings or ownership fail closed.

Files presents the personal namespace as **My files**. Its root cannot be renamed, moved or deleted through ordinary file operations. Breadcrumbs and move destinations stop at the namespace boundary. The hidden structural anchor is not a browsable shared workspace.

Personal namespaces are private by default. Explicit item sharing permits access to child files and folders, without exposing the personal root. Administrator status and old global-root grants provide no implicit access. These are application authorization guarantees, not encryption against storage operators. Existing bound personal homes are retained; unrelated unmanaged entries are not adopted or deleted automatically.

## Caller permissions

Full node summaries include five permission flags:

- `can_discover`: discover the node and its metadata.
- `can_read`: read content where supported.
- `can_write`: create children and perform eligible updates.
- `can_delete`: delete a file; directories report false because their deletion is unsupported.
- `can_share`: manage direct file/folder sharing; namespace roots report false.

Permissions add the containing namespace's baseline, item ownership, matching direct grants and recursive folder grants within that namespace. Grants at the structural global root do not inherit into namespaces. Unmanaged nodes remain inaccessible even when ownership or grants exist. Removing one source of access does not revoke rights supplied by another. These flags describe the current caller. For the authority and scope of changing an item's direct grants, see [File and folder sharing](filesystem-sharing.md).

Permission metadata accompanies full summaries from browsing, creation, updates and completed uploads. Sparse breadcrumbs, deletion acknowledgements and unpublished session instructions are not full summaries. Downloads independently enforce authorization.

## Visibility

`visible_to` has two states:

- `namespace` identifies the governing `namespace_id`, its `kind` (`personal` or `shared`) and display `name`. The descriptor identifies the containing namespace, not every source of item access.
- `restricted` supplies no namespace details when discovery has been lost. It must not be interpreted as private or as an empty audience.

Visibility does not enumerate group members, disclose another owner's identity or expose direct node grants. Namespace baseline access applies to every descendant and can be supplemented, but not reduced, by individual shares. A personal namespace descriptor alone does not prove an item is private. Moves remain within a namespace and preserve its governing policy. See [Namespace access](filesystem-namespaces.md) and [File and folder sharing](filesystem-sharing.md).
