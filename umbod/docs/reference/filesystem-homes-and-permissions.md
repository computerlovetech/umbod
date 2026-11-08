---
type: Reference
title: Filesystem homes and permissions
description: Personal upload destinations and caller-specific permission and visibility metadata.
---

# Filesystem homes and permissions

## Choosing a destination for an agent upload

When the user says “upload it to Umbod” without choosing a destination, use the `home` operation of `filesystem_browse`. This operation takes no target, path, user, or issuer. It resolves the authenticated caller's home and provisions it privately on first use. It returns the home node and permission-safe breadcrumbs; use `ls` with the returned node UUID to list its contents.

First-use provisioning changes tool eligibility through the existing event-synchronized runtime. Refresh tool discovery when upload tools have not yet appeared; do not interpret that reconciliation delay as a denial of the returned home permissions.

Use the returned node's `id` as the upload's `parent_id`. Check `permissions.can_write` rather than inferring write access from a folder name, administrator role, or `sharing.can_share`. Inspect `visible_to` separately from manageable sharing information. Permission metadata is a point-in-time snapshot, not a reservation: subsequent operations still check current authorization. Metadata-update responses capture access information within the mutation transaction, so later revocation does not turn a committed update into a reported authorization failure.

For an existing local file, compute its exact byte count and preferably its SHA-256 programmatically. Use `filesystem_begin_upload`, transfer the original bytes using its HTTP instructions, and call `filesystem_complete_upload`. Do not reconstruct local contents as generated text, invent a checksum, or treat a display name as a writable path. The [upload transfer reference](filesystem-upload-transfers.md) describes credentials, limits and retries.

After completion, report the returned file identity, verified size and SHA-256, and the file's own `visible_to` information. Do not report success before completion. Do not infer the file's audience from its parent folder or from an earlier upload receipt. Restricted or unavailable visibility must be reported as unknown, not private.

## Personal homes and the shared root

The shared root remains the canonical filesystem root. A home is an ordinary directory beneath it, owned by its authenticated user and initially created with no sharing grants. Creating a home does not require permission to discover or write to the shared root and does not grant either permission.

Home identity is bound to the exact authenticated issuer and user identifier. The durable binding, not a name or path, identifies the home. Default names use `Home-` followed by an opaque UUID to preserve sibling-name uniqueness without putting user identities in directory names. Renaming a home does not change its identity or cause another home to be created.

Repeated and concurrent home requests resolve the same directory. Lookup never adopts an existing folder merely because its name resembles a home. Missing or inconsistent ownership and binding state fails closed instead of selecting another user's folder or silently replacing policy.

Shared-root browsing filters each child independently. Administrator status or access to the root does not reveal another user's unshared home. A user can explicitly share their home under the existing sharing rules; home lookup does not reset those choices. These are application authorization guarantees, not encryption against operators of the underlying storage.

The web Files page opens directly into the caller's home, provisioning it on first use, and presents it as **Files** rather than a separate `Home-<UUID>` folder. Breadcrumbs and move destinations stop at this personal root and keep its internal name out of headings, upload destinations and sharing dialogs. This presentation follows the durable home binding even after a rename. Explicit node links outside the home remain available under existing permissions; the canonical root is labelled **Shared files** and retains its explicit node UUID link. No existing nodes are moved or renamed.

REST exposes the same caller-only operation through POST `/api/me/filesystem/home`. The `/api/me` prefix identifies the caller; it does not turn the entire filesystem into a personal namespace. Existing root browsing and explicit node UUIDs retain their meaning. A home is not a new `/me` path alias or a working directory.

## Caller permissions

Full node summaries include a `permissions` object with `can_discover`, `can_read`, `can_write`, `can_delete`, and `can_share`. Values describe the current caller, including matching direct user and group grants and ownership. Directory deletion remains unsupported, so directories report `can_delete` as false.

These fields are separate from MCP `sharing` metadata, which describes the direct user and group grants that the caller can manage. Being unable to manage sharing does not imply being unable to write. Conversely, sharing authority does not grant write permission.

Permission metadata accompanies full node summaries returned by browsing, creation, metadata changes and completed uploads. Sparse breadcrumb items, deletion acknowledgements and unpublished upload-session instructions are not full node summaries. Content downloads continue to enforce their existing authorization rules.

## Visibility is a policy description

`visible_to` has three explicit states:

- `available` describes the owner and the node's actual direct grants, scoped as `direct_node_policy`. It is available to callers authorized to inspect the policy, not merely to write the node.
- `restricted` means the caller cannot inspect the policy. This is not evidence of owner-only access.
- `unavailable` means the policy cannot be represented reliably. It must not be replaced by an empty audience.

An available policy includes direct principals even when those principals are not present in the manageable sharing projection. An empty manageable-grant list alone never establishes privacy. An available owner-only policy with no actual grants describes the default state of newly created private homes and files.

`group_members_expanded` is false: group grants identify groups, not a complete enumeration of their members. Discover permission governs node metadata; reading file content additionally requires read permission. Effective rights can combine grants for multiple principals belonging to the same caller, so the policy is not a complete list of individual readers.

Parent grants are not inherited. A shared root or shared home does not automatically share newly uploaded files. Any stored recursive flag remains a policy fact, not a promise that recursive inheritance is implemented. Administrator membership supplies no implicit filesystem override.

Visibility returned after a write describes that node's policy. A repeated upload completion retains its verified byte receipt while resolving current caller permissions and visibility, rather than claiming the original audience remains unchanged.
