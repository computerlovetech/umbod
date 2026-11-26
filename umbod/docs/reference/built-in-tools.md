# Built-in MCP tools

Use this reference to check what the file-sharing and administrator tools accept and return. For the full list available to your account, call `tools/list` on your Umbod MCP endpoint. The response includes each tool’s `inputSchema` and `outputSchema`, with the required fields and valid values. Which tools you see depends on your permissions and the features enabled on the server.

## Filesystem sharing tools

These tools are available through the ordinary MCP endpoint. See [file and folder sharing](../operations/filesystem-sharing.md) for access rules and REST policy management.

### `filesystem_search_sharing_recipients`

| Input field | Contract |
| --- | --- |
| `node_id` | Required node UUID. |
| `query` | Required nonblank search text, trimmed, at most 200 characters. |
| `recipient_type` | Optional `group` or `user`; omission searches both. |

Matching is a case-insensitive literal substring with normalized whitespace. Groups match IDs or labels; users match names only, not email addresses or subjects. Results contain `recipients` and `has_more`, with at most 50 eligible recipients, groups first. There are no limit, offset, or cursor arguments; narrow the query when `has_more` is true.

Each result has `type`, `label`, and either `group_id` or `user_id`. Discovery neither creates recipients nor grants access.

### `filesystem_share`

| Input field | Contract |
| --- | --- |
| `node_id` | Required node UUID. |
| `recipient` | Required typed target: `type=group` with `group_id`, or `type=user` with `user_id`. Omit the search result's label. |
| `permissions` | Nonempty list drawn from `discover`, `read`, `write`, `delete`, and `share`. |
| `recursive` | Optional boolean. Omission preserves existing scope, defaults true for new directories. Files always normalize to false. |

For ordinary read access, request both `discover` and `read`. The tool adds permissions to the recipient’s existing manageable share. It does not remove permissions or change other recipients, and repeating a request does not add another share. It can extend a share to the contents of a folder (`recursive: true`), but cannot undo that with `false`. Extending the share counts as a change even when the permissions stay the same.

The response contains `node_id`, `recipient`, `permissions`, required `recursive`, `changed`, and `visible_to`. The returned permissions are the recipient’s updated direct grant, not your own permissions or just the permissions you added. `visible_to` describes the storage area (namespace) containing the item. It does not list everyone with access or show direct grants.

Legacy requests using top-level `group_id` instead of `recipient` remain supported, returning `node_id`, `group_id`, `permissions`, required `recursive`, `changed`, and `visible_to`. Do not mix legacy and canonical target fields.

### Tool schema compatibility

`filesystem_search_sharing_recipients` replaces `filesystem_list_sharing_groups` and `search_users`; the removed names have no aliases. Refresh cached discovery results rather than invoking those names.

Search inputs and share inputs/outputs advertise alternative `anyOf` schema branches. Clients must resolve the advertised branches and references rather than assuming one flat object with every field. A canonical share returns a typed recipient; a legacy group share retains its legacy identity fields. Both include the containing namespace descriptor or restricted visibility. MCP's legacy compatibility does not apply to REST policy replacement.

## Administrator tools

[Administrator MCP endpoint](../operations/admin-mcp.md) · Full JSON Schemas: `tools/list` → `inputSchema`, `outputSchema`.

Input: `request` object with `operation` and the fields below (`?` = optional). Success: `structuredContent.result` contains `{operation, result}`; the table describes the inner `result`.

| Tool | `request.operation` | Other `request` fields | `result` |
| --- | --- | --- | --- |
| `admin_discover` | `list_connectors` | — | `[{connector, display_name, publication_state, authorization_mode}]` |
| `admin_discover` | `list_groups` | — | `[{group_id, label, description, revision}]` |
| `admin_discover` | `list_permission_targets` | — | `{connectors, capabilities}`: assignable targets with exact IDs or keys and display names |
| `admin_discover` | `search_users` | `query` (1–200 characters after trimming, matches name or email), `limit?` (1–100, default 20) | `{users: [{user_id, name, email, last_seen_at}], has_more}`; observed users only |
| `admin_discover` | `list_namespaces` | — | Array of shared namespace views |
| `admin_inspect` | `read_connector_configuration` | `connector` | Connector state |
| `admin_inspect` | `read_group_permissions` | `group_id` | `{group_id, connector_ids, capabilities}`; direct grants, including stale targets |
| `admin_apply` | `update_connector_configuration` | `connector`, `desired_state` | Updated connector state |
| `admin_apply` | `update_group_permissions` | `group_id`, `connectors?`, `capabilities?`; at least one change | `{group_id, status: "applied"}` |
| `admin_apply` | `create_namespace` | `namespace: {name, groups, description?}` | Created shared namespace view |
| `admin_apply` | `update_namespace` | `namespace_id`, `namespace: {name, groups, expected_revision, description?, expected_root_revision?}`; supply both optional fields together | Updated shared namespace view |

- **Connector reference:** `{connector_kind, connector_id}`. Kinds: `native`, `openapi`, `downstream_mcp`.
- **Connector state:** `{connector, capabilities, capability_description, group_permissions}`. Capabilities include activation and, for tools, invocation policy and revision. Description state includes its revision.
- **Group patch:** `connectors` entries are `{connector_id, permission_status}`; `capabilities` entries are `{capability: {connector_id, capability_kind, capability_key}, permission_status}`. `enabled` adds a grant; `disabled` removes it. Omitted targets stay unchanged.
- **Shared namespace view:** `{id, root_node_id, name, groups, description, revision, root_revision}`. Group entries are `{group_id, access}` (`read` or `read_write`). Updates replace the full group list; an empty `description` clears it.

### `desired_state.operations`

Each entry has an `operation` tag and the fields below.

| Operation | Fields | Purpose |
| --- | --- | --- |
| `set_capability_activation` | `capability_kind`, `capability_key`, `activation_status` | Enable or disable a capability. |
| `set_capability_invocation_policy` | `capability_kind`, `capability_key`, `mode`, `expected_revision` | Set a tool to `direct` or `ask`. |
| `set_capability_description` | `description`, `expected_revision` | Override the connector capability description. |
| `use_system_capability_description` | `expected_revision` | Restore the system description. |
| `update_group_permissions` | `group_id`, `connector_status`, `capabilities` | Change connector and/or capability grants for a group. |

Omitted settings stay unchanged; omitted or empty `operations` reads current state. Capability kinds: `tool`, `prompt`, `resource`, `resource_template`. Invocation policies are tool-only.
