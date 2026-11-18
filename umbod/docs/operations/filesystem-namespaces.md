---
type: Reference
title: Filesystem namespaces
description: Namespace discovery, administrator group assignments and authoritative access boundaries.
---

# Filesystem namespaces

## Access model

Every accessible node belongs to one registered personal or shared namespace. Its policy supplies baseline access for the root and every descendant; item ownership and explicit shares can add permissions below that root. The hidden structural root and unmanaged entries are inaccessible regardless of old ownership or direct and recursive grants. Retiring access does not remove stored entries or bytes.

Personal namespaces are private by default and bound to an exact trusted owner identity. Explicit file/folder shares allow recipient access; administrator status alone does not. Administrators manage shared namespaces and assign existing registered groups either `read` or `read_write` access. Management authority does not grant content access. Item ownership retains its existing permissions, including the authority to share individual files and folders.

Read grants `discover` and `read`. Read/write also grants `write` and `delete`, subject to operation support. Individual file and folder grants are additive, not restrictive overrides. Removing an assignment removes that group's baseline contribution; other groups, item ownership and explicit shares can still authorize access. Each content read and pending upload operation checks the resulting current permissions.

## Caller discovery

`GET /api/me/filesystem/namespaces` returns a `namespaces` list: the caller's personal namespace followed by accessible shared namespaces. Entries contain `id`, `root_node_id`, `name`, `description`, `kind` and effective `permissions`. First use provisions a stable personal namespace.

MCP `filesystem_browse` operation `namespaces` provides the same discovery without a target. Namespace descriptions are included in both structured output and model-readable text. Operation `home` resolves the private default upload destination. Root and absolute-path targets refer to personal files. Use returned root UUIDs to select shared namespaces.

## Administration

Administrator routes are:

- `GET /api/admin/filesystem/namespaces`: list shared configurations.
- `POST /api/admin/filesystem/namespaces`: create from `name`, `groups` and an optional `description`.
- `PUT /api/admin/filesystem/namespaces/{namespace_id}`: replace the name and assignments using the current `expected_revision`; optionally update the description using `expected_root_revision`.
- `DELETE /api/admin/filesystem/namespaces/{namespace_id}`: delete an empty shared namespace. Supply both `expected_revision` and `expected_root_revision` in the JSON body. Success returns `204 No Content`.

A shared namespace exists independently of groups and can be created with `groups: []` before any groups are registered. Its name is unique among shared namespaces, not tied to a group or reserved by an unmanaged storage entry. Multiple groups can receive access to the same namespace and root UUID.

Assignments contain a registered `group_id` and `access` of `read` or `read_write`. Empty assignments leave the namespace root inaccessible through content operations. Responses contain `id`, `root_node_id`, `name`, `description`, positive `revision` and `root_revision`, and `groups`. Personal policies cannot be administered through these routes.

Descriptions use the namespace root's `metadata.attributes.description`, matching ordinary file and folder browsing. Existing roots without that attribute return an empty description. Creating without a description leaves it empty; an explicit empty string clears it. Descriptions are untrusted text and do not affect access.

Omitting `description` when saving preserves it, including during grant-only updates. Supplying it requires the current `expected_root_revision` as well as `expected_revision`. This prevents administration from overwriting a concurrent root metadata edit through ordinary file operations. Name, description and assignment changes are atomic.

Stale saves return `409` with `filesystem_policy_stale`; reread and reconcile rather than blindly replaying. Invalid assignments return `422`. Saved grants are bound to their configured trusted issuer; ordinary editing cannot silently rebind them after an issuer change. A referenced group cannot be deleted until its assignments are removed.

In **Group permissions → Filesystem**, choose **Delete namespace** on the shared namespace’s row and confirm. Group assignments do not prevent deletion. Any stored child blocks it, including an empty folder or an entry the administrator cannot see. An active upload targeting the root also blocks deletion. The API returns `409` with `filesystem_namespace_not_empty` or `filesystem_namespace_active_uploads`, respectively. If the response is `filesystem_policy_stale`, reload the namespace and confirm again. Deletion is never recursive and does not remove stored bytes.

## Boundaries

Namespace roots cannot be renamed, moved or deleted through ordinary file operations. Cross-namespace moves are rejected atomically. Breadcrumbs stop at the namespace root. Normal file operations remain available inside each namespace according to the caller's permissions.

Global-root browsing and root-access administration have been removed without compatibility aliases. Per-node sharing remains available below namespace roots, with recursive inheritance bounded by the namespace. Existing unmanaged data is retained, not automatically imported. Personal namespace deletion and physical content garbage collection are unsupported.

See [Files](../using-umbod/files.md), [File and folder sharing](filesystem-sharing.md), [Homes and permissions](filesystem-homes-and-permissions.md) and [Upload transfers](filesystem-upload-transfers.md).
