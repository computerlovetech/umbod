---
type: Reference
title: File and folder sharing
description: Additive individual file and folder grants within personal and shared namespaces.
---

# Filesystem sharing

Use an item share to add access to a file or folder inside a registered namespace. To grant baseline access to a whole workspace, use [namespace administration](filesystem-namespaces.md#administration) instead; these item interfaces cannot share a namespace root.

Before changing a share, check the following:

- **Caller:** every sharing operation checks current `discover` and `share` on the selected node, whether direct or inherited. Administrator membership alone is not enough.
- **Folder scope:** a new directory grant defaults to `recursive: true` if omitted. It covers current and future descendants within the namespace. Set `recursive: false` for the directory alone. Omitting scope on an existing grant preserves its stored value; set true explicitly to widen a legacy false grant. File grants always normalize to false.
- **Other access:** direct grants and recursive ancestor grants add to namespace baseline rights. Removing one grant does not cancel rights from another source. Inheritance stops at the namespace root, and ownership never inherits or transfers.

To check the result in the workspace, use [Files](../using-umbod/files.md#share-files-and-folders). Test discovery with the affected account: manageable sharing summaries show direct grants, not everyone with access. Full node summaries describe caller permissions and the containing namespace separately. See [Homes and permissions](filesystem-homes-and-permissions.md) for `visible_to` and why it is not an access audit.

After a move, Umbod immediately checks inherited access using the new parent folders. Check the result at the new location. The moved subtree keeps its direct grants and ownership; no grants are copied, and there is no move-preview API.

## Recipient identity and discovery

Groups must already be registered. User recipients come from Umbod's login-observed directory and resolve to an exact identity under the configured issuer. User discovery and user-scoped policy replacement require upstream-verified authentication under that issuer, including replacement with an empty grant list. Group-only discovery does not require user-directory authority.

If a person is missing from search, check that they have signed in with a verified identity under the configured issuer. The directory can be incomplete or contain old entries. Search cannot tell you whether an account is active. Do not send an email, subject, issuer, or display label as a mutation target; use the returned `type` and `group_id` or opaque `user_id`.

See the [built-in tool reference](../reference/built-in-tools.md#filesystem-sharing-tools) for recipient search and additive sharing inputs, outputs, and schema compatibility.

## List incoming shares with REST

`GET /api/me/filesystem/shared-with-me` returns `nodes` for the current caller. It lists discoverable items with explicit user or group grants to the caller, once per item. Descendants visible only through a recursive folder share are browsed within that folder instead. The list does not grant additional access or change either the containing namespace or the original item link.

## Search recipients with REST

`GET /api/me/filesystem/nodes/{node_id}/access/recipients` accepts required `query` and optional `recipient_type=group|user`. Omission searches both types. It uses the same core search, validation, authorization and typed `recipients`/`has_more` result as `filesystem_search_sharing_recipients`.

## Inspect and replace policy with REST

Resource: `/api/me/filesystem/nodes/{node_id}/access`.

### Read

`GET` accepts optional `recipient_type=group` or `recipient_type=user`; omission returns both types. The response contains `node_id`, `revision`, `grants`, and `blocked_recipients`. Each grant contains a labelled typed `recipient`, `permissions`, and the actual persisted `recursive` boolean. Read sharing summaries use the same grant contract. These lists describe manageable direct grants, not inherited access or where it came from.

The response's strong quoted `ETag` is the revision to use for replacement. Even filtered reads carry the revision of the whole policy: a user-grant change can invalidate an editor showing only groups.

### Replace

`PUT` requires exactly one `recipient_type` query value, either `group` or `user`, and an `If-Match` header copied from the latest GET's `ETag`. The body contains `grants`, each with an unlabelled typed `recipient`, a nonempty `permissions` list, and `recursive` scope (omission preserves existing scope, defaults true for new directories, always normalized false for files). Recipients must be unique and match the selected type. Display labels and caller-selected issuer/subject values are not accepted. When editing scope, send back the returned `recursive` value for every grant you are not changing. Older clients omitting scope preserve existing legacy false grants. Replacement may explicitly widen or narrow the supplied scope; changing only scope changes the policy revision.

Replacement affects only manageable grants of the selected type. An empty `grants` list clears that scope while preserving the other recipient type and protected grants. Inspect the updated response and `ETag` after success. Successful PUT responses additionally include `visible_to`; GET policy views retain their existing fields. Visibility can be restricted if the caller no longer has policy inspection authority after replacement.

| Condition | HTTP status |
| --- | --- |
| Missing `If-Match` | `428` |
| Invalid `If-Match`, including weak, wildcard, or unquoted revisions | `422` |
| Stale revision | `412` |
| Missing, repeated, or invalid PUT `recipient_type` | `422` |

After `412`, get the current policy and compare it with your intended changes before retrying. Do not replay a replacement unchanged against the new revision.

### REST migration and boundaries

The previous groups-only node-access request body is no longer accepted. Migrate node-policy clients to typed `grants`, an explicit replacement scope, and ETag-based concurrency. The group-specific recipient catalogue has been removed; use unified recipient search. Do not confuse node-policy replacement with administrator namespace management, which uses `groups` and `expected_revision`. The former global-root administration API is removed.

The browser sharing dialog edits groups or users separately, searching through the unified recipient endpoint and saving only the selected type. Switching types with unsaved changes requires confirmation. Neither policy views nor sharing summaries are complete effective-access audits. Registered, representable recursive grants are manageable. Malformed, unresolved, and foreign-issuer grants remain protected rather than being silently removed. Existing false grants are never migrated or copied automatically.
