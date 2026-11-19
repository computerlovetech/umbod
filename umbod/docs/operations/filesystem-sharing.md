---
type: Reference
title: File and folder sharing
description: Additive individual file and folder grants within personal and shared namespaces.
---

# Filesystem sharing

These contracts manage grants stored directly on a file or directory. New directory grants default to `recursive: true` when scope is omitted. Omitting scope on an existing grant preserves its persisted value; explicit true is required to widen a legacy false grant. Recursive directory grants apply to current and future descendants. Explicit `recursive: false` grants affect only the selected node; file grants always normalize to false. Effective permissions add direct and recursive ancestor grants without subtracting other grants. Item ownership never inherits or transfers. Namespace baseline rights also apply; item grants cannot narrow them. Shares require a node inside a registered namespace, and recursive inheritance stops at its root. Namespace roots use separate administration and cannot be shared through these item interfaces. Every operation checks current `discover` and `share` authority on the selected node, whether direct or inherited; administrator membership alone is insufficient. See [Files](../using-umbod/files.md) for the workspace controls and permission meanings.

Moves immediately reevaluate inherited access from the destination ancestry while retaining the moved subtree's direct grants and ownership; no grant copies or move-preview APIs are involved.

Full node summaries separately report caller permissions and the containing namespace descriptor. Neither that descriptor nor manageable sharing summaries are complete effective-access audits. See [Homes and permissions](filesystem-homes-and-permissions.md) for private default upload destinations and the meaning of `visible_to`.

## Recipient identity and discovery

Groups must already be registered. User recipients come from Umbod's login-observed directory and resolve to an exact identity under the configured issuer. User discovery and user-scoped policy replacement require upstream-verified authentication under that issuer, including replacement with an empty grant list. Group-only discovery does not require user-directory authority.

The directory can be incomplete or historical. Search is not an account-activity check. Do not send an email, subject, issuer, or display label as a mutation target; use the returned `type` and `group_id` or opaque `user_id`.

See the [built-in tool reference](../reference/built-in-tools.md#filesystem-sharing-tools) for recipient search and additive sharing inputs, outputs, and schema compatibility.

## List incoming shares with REST

`GET /api/me/filesystem/shared-with-me` returns `nodes` for the current caller. It lists discoverable items with explicit user or group grants to the caller, once per item. Descendants visible only through a recursive folder share are browsed within that folder instead. The list does not grant additional access or change either the containing namespace or the original item link.

## Search recipients with REST

`GET /api/me/filesystem/nodes/{node_id}/access/recipients` accepts required `query` and optional `recipient_type=group|user`. Omission searches both types. It uses the same core search, validation, authorization and typed `recipients`/`has_more` result as `filesystem_search_sharing_recipients`.

## Inspect and replace policy with REST

Resource: `/api/me/filesystem/nodes/{node_id}/access`.

### Read

`GET` accepts optional `recipient_type=group` or `recipient_type=user`; omission returns both types. The response contains `node_id`, `revision`, `grants`, and `blocked_recipients`. Each grant contains a labelled typed `recipient`, `permissions`, and the actual persisted `recursive` boolean. Read sharing summaries use the same grant contract. These lists describe manageable direct grants, not inherited audiences or provenance.

The response's strong quoted `ETag` is the revision to use for replacement. Even filtered reads carry the revision of the whole policy: a user-grant change can invalidate an editor showing only groups.

### Replace

`PUT` requires exactly one `recipient_type` query value, either `group` or `user`, and an `If-Match` header copied from the latest GET's `ETag`. The body contains `grants`, each with an unlabelled typed `recipient`, a nonempty `permissions` list, and `recursive` scope (omission preserves existing scope, defaults true for new directories, always normalized false for files). Recipients must be unique and match the selected type. Display labels and caller-selected issuer/subject values are not accepted. Roundtrip every grant's returned recursive value explicitly when editing scope. Older clients omitting scope preserve existing legacy false grants. Replacement may explicitly widen or narrow the supplied scope; changing only scope changes the policy revision.

Replacement affects only manageable grants of the selected type. An empty `grants` list clears that scope while preserving the other recipient type and protected grants. Inspect the updated response and `ETag` after success. Successful PUT responses additionally include `visible_to`; GET policy views retain their existing fields. Visibility can be restricted if the caller no longer has policy inspection authority after replacement.

| Condition | HTTP status |
| --- | --- |
| Missing `If-Match` | `428` |
| Invalid `If-Match`, including weak, wildcard, or unquoted revisions | `422` |
| Stale revision | `412` |
| Missing, repeated, or invalid PUT `recipient_type` | `422` |

On a stale revision, reread and reconcile the policy before retrying. Do not blindly replay a replacement against a new revision.

### REST migration and boundaries

The previous groups-only node-access request body is no longer accepted. Migrate node-policy clients to typed `grants`, an explicit replacement scope, and ETag-based concurrency. The group-specific recipient catalogue has been removed; use unified recipient search. Do not confuse node-policy replacement with administrator namespace management, which uses `groups` and `expected_revision`. The former global-root administration API is removed.

The browser sharing dialog edits groups or users separately, searching through the unified recipient endpoint and saving only the selected type. Switching types with unsaved changes requires confirmation. Neither policy views nor sharing summaries are complete effective-access audits. Registered, representable recursive grants are manageable. Malformed, unresolved, and foreign-issuer grants remain protected rather than being silently removed. Existing false grants are never migrated or copied automatically.
