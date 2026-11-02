# Filesystem sharing

These contracts apply to direct sharing of a file or directory. They do not transfer ownership, share descendants, or initialize root access. Every operation checks current `discover` and `share` authority on the selected node; administrator membership alone is insufficient. See [Files](../using-umbod/files.md) for the workspace controls and permission meanings.

Full node summaries separately report caller permissions and direct-policy visibility. These are not the manageable sharing projection described below. See [Homes and permissions](filesystem-homes-and-permissions.md) for private default upload destinations and the meaning of `visible_to`.

## Recipient identity and discovery

Groups must already be registered. User recipients come from Umbod's login-observed directory and resolve to an exact identity under the configured issuer. User discovery and user-scoped policy replacement require upstream-verified authentication under that issuer, including replacement with an empty grant list. Group-only discovery does not require user-directory authority.

The directory can be incomplete or historical. Search is not an account-activity check. Do not send an email, subject, issuer, or display label as a mutation target; use the returned `type` and `group_id` or opaque `user_id`.

### `filesystem_search_sharing_recipients`

Available through the root MCP endpoint.

| Input field | Contract |
| --- | --- |
| `node_id` | Required node UUID. |
| `query` | Required nonblank search text, trimmed, at most 200 characters. |
| `recipient_type` | Optional `group` or `user`; omission searches both. |

Matching is a case-insensitive literal substring with normalized whitespace. Groups match IDs or labels; users match names only, not email addresses or subjects. Results contain `recipients` and `has_more`, with at most 50 eligible recipients, groups first. There are no limit, offset, or cursor arguments; narrow the query when `has_more` is true.

Each result has `type`, `label`, and either `group_id` or `user_id`. Discovery neither creates recipients nor grants access.

## Add permissions with MCP

### `filesystem_share`

| Input field | Contract |
| --- | --- |
| `node_id` | Required node UUID. |
| `recipient` | Required typed target: `type=group` with `group_id`, or `type=user` with `user_id`. Omit the search result's label. |
| `permissions` | Nonempty list drawn from `discover`, `read`, `write`, `delete`, and `share`. |

For ordinary read access, request both `discover` and `read`. The operation unions the requested permissions with the recipient's existing manageable direct grant. It preserves other permissions and recipients, is idempotent, and cannot revoke access.

The response contains `node_id`, `recipient`, `permissions`, `changed`, and `visible_to`. Returned permissions are the authoritative recipient union, not the caller's own permissions or just the requested additions. Visibility describes the actual direct policy, not only manageable grants.

Legacy requests using top-level `group_id` instead of `recipient` remain supported, returning `node_id`, `group_id`, `permissions`, `changed`, and `visible_to`. Do not mix legacy and canonical target fields.

### Tool schema compatibility

`filesystem_search_sharing_recipients` replaces `filesystem_list_sharing_groups` and `search_users`; the removed names have no aliases. Refresh cached discovery results rather than invoking those names.

Search inputs and share inputs/outputs advertise alternative `anyOf` schema branches. Clients must resolve the advertised branches and references rather than assuming one flat object with every field. A canonical share returns a typed recipient; a legacy group share retains its legacy identity fields. Both include additive visibility metadata. MCP's legacy compatibility does not apply to REST policy replacement.

## Inspect and replace policy with REST

Resource: `/api/me/filesystem/nodes/{node_id}/access`.

### Read

`GET` accepts optional `recipient_type=group` or `recipient_type=user`; omission returns both types. The response contains `node_id`, `revision`, `grants`, and `blocked_recipients`. Each grant contains a labelled typed `recipient` and `permissions`.

The response's strong quoted `ETag` is the revision to use for replacement. Even filtered reads carry the revision of the whole policy: a user-grant change can invalidate an editor showing only groups.

### Replace

`PUT` requires exactly one `recipient_type` query value, either `group` or `user`, and an `If-Match` header copied from the latest GET's `ETag`. The body contains `grants`, each with an unlabelled typed `recipient` and a nonempty `permissions` list. Recipients must be unique and match the selected type. Display labels, caller-selected issuer/subject values, and recursive sharing are not accepted.

Replacement affects only manageable grants of the selected type. An empty `grants` list clears that scope while preserving the other recipient type and protected grants. Inspect the updated response and `ETag` after success. Successful PUT responses additionally include `visible_to`; GET policy views retain their existing fields. Visibility can be restricted if the caller no longer has policy inspection authority after replacement.

| Condition | HTTP status |
| --- | --- |
| Missing `If-Match` | `428` |
| Invalid `If-Match`, including weak, wildcard, or unquoted revisions | `422` |
| Stale revision | `412` |
| Missing, repeated, or invalid PUT `recipient_type` | `422` |

On a stale revision, reread and reconcile the policy before retrying. Do not blindly replay a replacement against a new revision.

### REST migration and boundaries

The previous groups-only node-access request body is no longer accepted. Migrate node-policy clients to typed `grants`, an explicit replacement scope, and ETag-based concurrency. Do not confuse this with the administrator root-access API, which still uses `groups` and `expected_revision`, or the group-specific `/access/eligible-groups` endpoint.

The browser sharing dialog uses group-scoped replacement and does not edit user grants. Neither policy views nor sharing summaries are complete effective-access audits. Recursive, malformed, unresolved, and foreign-issuer grants remain protected rather than being silently removed.
