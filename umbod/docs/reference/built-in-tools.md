---
description: Contracts for the built-in Umbod MCP tools for files, sharing, agent diagnostics, and administration.
---

# Built-in MCP tools

Use this reference to choose an Umbod built-in tool and understand its behavior. For the exact contract on your deployment, call `tools/list` on the relevant MCP endpoint and read the tool’s `inputSchema` and, when advertised, its `outputSchema`. Discovery reflects the signed-in caller’s permissions and the server’s configuration. Tools supplied by connectors are not covered here. On a tool failure, follow the recovery guidance in the returned content rather than assuming the operation did not run. See [response diagnostics](#response-guidance) for request correlation and operation states.

- [Filesystem tools](#filesystem-tools) and [sharing](#filesystem-sharing-tools) use the [ordinary MCP endpoint](../use/connect-agents.md#with-any-mcp-client).
- [Agent diagnostics](#agent-diagnostics) uses the ordinary MCP endpoint and requires diagnostic reporting to be enabled.
- [Administrator tools](#administrator-tools) use the private administrator endpoint by default, or the ordinary endpoint when shared hosting is configured.
- [Connector discovery and execution](#connector-discovery-and-execution) depends on the configured connector tool exposure mode.

## Filesystem tools

These tools are permission-filtered and are not available on connector-scoped endpoints. Node and parent IDs are UUIDs. See [agent file access](#reading-and-uploading-files) for resource reads and destination selection.

| Tool | Main inputs | Successful result |
| --- | --- | --- |
| `filesystem_browse` | `operation` and operation-specific fields (below). | `{operation, result}` in `structuredContent`, without file bytes. |
| `get_filesystem_node` | `node_id`. | Node summary, with a resource link for a file. |
| `list_filesystem_children` | `parent_id`. | `{nodes}` containing discoverable children, with resource links for files. |
| `create_filesystem_directory` | `parent_id`, `name`, `metadata`. | Summary of the new empty directory. |
| `create_filesystem_file` | `parent_id`, `name`, `metadata`. | Summary and resource link for the new empty file. |
| `update_filesystem_node` | `node_id`, current `expected_revision`, and at least one of `name`, `parent_id`, or `metadata`. | Updated node summary. Omitted fields and file bytes are preserved. Moves stay within a namespace; namespace roots allow metadata changes only. |
| `filesystem_delete_file` | `node_id` and current `expected_revision`. | `{node_id, deleted: true}`. File only; no trash, restore, or secure erasure. Human confirmation is required by default. |
| `filesystem_upload` | `parent_id`, `name`, `metadata`, and `content` with `encoding: utf-8` and `text`, or `encoding: base64` and `data` (canonical padded base64). | New file summary (without `sharing`) and resource link. The decoded size limit is 10 MiB, subject to lower server limits. |
| `filesystem_begin_upload` | `parent_id`, `name`, `metadata`, exact `size_bytes`, and optional lowercase hexadecimal `expected_sha256`. | `upload_id`, `expires_at`, `transfer` instructions for HTTP PUT, and `complete_tool`. PUT alone does not publish. |
| `filesystem_complete_upload` | `upload_id` from begin, called as the session owner after transferring the bytes. | `{node, size_bytes, sha256}` and a resource link for the published file. |

Creation and upload metadata contains `content_type` (a string or an empty object for unspecified) and `attributes` (a map of strings to strings). For larger uploads, follow the [HTTP transfer workflow](#reading-and-uploading-files). Inline upload and begin are not idempotent. Completion can return the original verified receipt while the published file exists.

### `filesystem_browse`

| `operation` | Other inputs | Purpose |
| --- | --- | --- |
| `home` | None. | Resolve the private default destination, provisioning it if needed. |
| `namespaces` | None. | List personal and accessible shared namespaces with `root_node_id`. |
| `stat` | `target`. | Inspect one node and its breadcrumbs. |
| `ls` | `target`, optional `max_entries` (1–1,000, default 100). | List immediate children. |
| `tree` | `target`, optional `max_entries` (1–1,000, default 100) and `depth` (1–16, default 2). | Read a bounded directory tree. |

`target` is tagged with `type`: `root` takes no other fields, `path` requires an absolute `path` inside personal files, and `node` requires `node_id`. For a shared namespace, use the `node` target with its `root_node_id`; `root` and `path` address only personal files.

When deletion requires confirmation, a client may receive a nonterminal input-required result. Return the opaque `requestState` unchanged with the user’s explicit decision. Clients without supported confirmation cannot complete an approval-required deletion.

Read bytes with `resources/read` at `umbod://filesystem/files/{node_id}`, not a filesystem tool call. The URI identifies current content and does not grant access. Reads require current discover and read permission and return complete UTF-8 text or a base64 blob within the configured preview limit (default 1 MiB). Use authenticated HTTP download for larger files.

### Reading and uploading files

- **Find a destination:** `filesystem_browse` with operation `namespaces` lists the personal and shared namespaces. Operation `home` returns the personal default. Use the returned UUIDs as `parent_id`, never invented paths, and check `permissions.can_write`.
- **Read:** files have the URI `umbod://filesystem/files/{node_id}`. Read them with MCP `resources/read`. Text types return UTF-8 text, other types return base64. Reads are never truncated: a file above the preview limit fails, so download it over [REST](rest-api.md#files).
- **Upload a small file:** `filesystem_upload` with inline content.
- **Upload a large file:** call `filesystem_begin_upload` with the exact byte count, `PUT` the bytes to the returned URL with the returned headers and nothing else, then call `filesystem_complete_upload`. The file exists only after completion. Treat the URL as a secret. Sessions expire after one hour.
- **Retry safely:** begin is not idempotent. After an uncertain `PUT`, call complete instead of starting again.

## Filesystem sharing tools

Both tools require current `discover` and `share` permissions on the node and exclude namespace roots. User discovery requires verified authentication under the configured issuer. See [file and folder sharing](../use/files.md#share-a-file-or-folder) for access rules and the [file access API](rest-api.md#files) for REST policy management.

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

The response contains `node_id`, `recipient`, `permissions`, required `recursive`, `changed`, `visible_to`, and `view_url`. The returned permissions are the recipient’s updated direct grant, not your own permissions or just the permissions you added. `visible_to` describes the storage area (namespace) containing the item. It does not list everyone with access or show direct grants.

Legacy requests using top-level `group_id` instead of `recipient` remain supported, returning `node_id`, `group_id`, `permissions`, required `recursive`, `changed`, `visible_to`, and `view_url`. Do not mix legacy and canonical target fields. In both forms, `view_url` is an authenticated browser link, not a public share, download URL, or MCP resource URI. It is null when the caller cannot discover the node.

### Tool schema compatibility

`filesystem_search_sharing_recipients` replaces `filesystem_list_sharing_groups` and `search_users`; the removed names have no aliases. Refresh cached discovery results rather than invoking those names.

Search inputs and share inputs/outputs advertise alternative `anyOf` schema branches. Clients must resolve the advertised branches and references rather than assuming one flat object with every field. A canonical share returns a typed recipient; a legacy group share retains its legacy identity fields. Both include the containing namespace descriptor or restricted visibility. MCP's legacy compatibility does not apply to REST policy replacement.

## Agent diagnostics

Diagnostic reports are durable agent self-reports, not independently verified findings or application logs. These MCP capabilities are discoverable to eligible signed-in callers only when [diagnostic reporting is enabled](../use/insights.md#agent-diagnostics) and at least one enabled playbook has an enabled pattern.

| MCP capability | Name or URI | Contract |
| --- | --- | --- |
| Resource | `umbod://agent-behaviour/playbooks` | JSON with `configuration_revision` and `playbooks`, each with `id`, `name`, and `resource_uri`. |
| Resource template | `umbod://agent-behaviour/playbooks/{playbook_id}` | JSON with `configuration_revision`, `playbook`, `patterns`, `reporting_guidance`, and `resource_uri`. Read it for live collection instructions and the selected patterns. |
| Prompt | `run_diagnostics` | Requires `playbook_id`. Returns a user-role message directing the client to read that playbook’s current resource. Slash-command presentation depends on the client. |
| Tool | `report_diagnostic` | Submits an assessment of every pattern selected by the current playbook and returns a durable receipt. |

Read the live playbook before collecting or submitting a report, whether or not you use the prompt. If you cannot read it, stop without submitting. Neither the prompt nor the resource grants permission or submits a report. Use only authorized context, respect refusals and user and client policy, and omit transcripts, secrets, credentials, unnecessary personal data, and hidden reasoning.

### `report_diagnostic`

All fields are required and are passed directly as tool arguments, without a `request` wrapper.

| Input field | Contract |
| --- | --- |
| `idempotency_key` | UUID generated once before submission. It is scoped to the authenticated caller. |
| `configuration_revision` | Current revision from the playbook resource (integer ≥ 1). |
| `playbook_id` | ID of the playbook read for this assessment. |
| `trigger` | `user_requested` or `proactive`. Describes how diagnostics started; it does not grant permission or prove consent. |
| `assessments` | 1–20 entries with `pattern_id`, `status`, `summary`, and `evidence`. Include each selected pattern exactly once. |

`status` is `observed` (factual evidence of a match), `not_observed` (assessed without a match), or `not_assessed` (insufficient authorized context). `summary` is at most 1,000 characters and must be nonblank for `observed` and `not_assessed`. `evidence` is an array of zero to three nonblank factual strings, each at most 500 characters after trimming; it must be empty for `not_assessed`. The compact UTF-8 submission is limited to 32 KiB.

Success returns `structuredContent` with `report_id` (UUID), `received_at` (timestamp with timezone), and `duplicate` (boolean). While reporting is enabled and the deduplication receipt is unexpired, an identical repeat returns the original ID and timestamp with `duplicate: true`, unless the report was deleted. Reports expire after 30 days and deduplication receipts after 60 days. A duplicate receipt does not prove the report is still readable. Do not claim success until a receipt arrives.

- **Lost response or uncertain storage failure:** within the 60-day deduplication window, retry only the identical payload with the same `idempotency_key`. Never use a replacement key to retry an uncertain submission. After the window, even the same key can create a new report.
- **`stale_configuration`:** reload the playbook and reassess. Do not relabel old evidence with a new revision.
- **`reporting_disabled` or `instructions_unavailable`:** stop using the cached instructions. Rediscover once reporting is available and read a current playbook before collecting again.
- **`idempotency_conflict`:** the key belongs to different report data. Reconcile the original submission rather than replaying changed data.
- **`report_gone`:** the report was deleted. Do not resubmit it or generate a replacement key.

## Administrator tools

Use the [administrator MCP endpoint](../self-host/operate.md#administrator-mcp) and sign in with the required administrator membership. These tools configure existing connectors; they cannot create or publish them. Discover exact IDs, capability keys, and revisions before applying changes. If a write’s outcome is uncertain, inspect current state before retrying.

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
- **Group patch:** `connectors` entries are `{connector_id, permission_status}`; `capabilities` entries are `{capability: {connector_id, capability_kind, capability_key}, permission_status}`. `enabled` adds a grant; `disabled` removes it, not an explicit deny. Omitted targets stay unchanged.
- **Shared namespace view:** `{id, root_node_id, name, groups, description, revision, root_revision}`. Group entries are `{group_id, access}` (`read` or `read_write`). Updates replace the full group list; an empty `description` clears it.

### `desired_state.operations`

Each entry has an `operation` tag and the fields below.

| Operation | Fields | Purpose |
| --- | --- | --- |
| `set_capability_activation` | `capability_kind`, `capability_key`, `activation_status` | Enable or disable a capability. |
| `set_capability_invocation_policy` | `capability_kind`, `capability_key`, `mode`, `expected_revision` | Set a tool to `direct` or `ask`. |
| `set_capability_description` | `description`, `expected_revision` | Override the connector capability description. |
| `use_system_capability_description` | `expected_revision` | Restore the system description. |
| `update_group_permissions` | `group_id`, `connector_status?`, `capabilities?` | Change connector and/or capability grants for a group. Capability entries use `capability_kind`, `capability_key`, and `status`, not `permission_status`. |

Omitted settings stay unchanged; omitted or empty `operations` reads current state. Capability kinds: `tool`, `prompt`, `resource`, `resource_template`. Invocation policies are tool-only. Activation and invocation policy may target the same tool, but do not repeat a target within one operation type. Use at most one description operation and one permission operation per group, with unique capability targets within each group.

## Connector discovery and execution

These are Umbod’s entry points for discovering and calling connected-app tools. They are distinct from the tools supplied by connectors. Their availability depends on the server’s connector tool exposure mode and does not grant access to a connector.

| Exposure mode | Fixed tools |
| --- | --- |
| `flat` (default) | None. Accessible connector tools are listed directly. |
| `gateway` | `search_tools`, `execute_tool` |
| `codemode` | `search_tools`, `execute_code` |

| Tool | Input and result |
| --- | --- |
| `search_tools` | Requires `query` (nonempty text). Optional `limit` is 1–50 (default 10); optional `connector_ids` narrows the search. Returns `{matches}` with executable `tool_name`, `connector_id`, `operation_name`, `description`, `input_schema`, and `relevance_score`. |
| `execute_tool` | Requires `tool_name` from discovery and an `arguments` object matching the discovered input schema. Returns the selected connector tool’s result; there is no single output schema across connectors. |
| `execute_code` | Requires `code` (sandboxed Python using accessible connector tools). `structuredContent` reports `outcome` (`success`, `failure`, or `timeout`), `printed_output`, and `nested_calls`, plus `final_value` on success or `error` otherwise. Check individual call outcomes as well as the enclosing result; a later failure does not undo earlier calls. |

In `codemode`, an OpenAPI search match can name `execute_openapi`. This is a function inside the `execute_code` sandbox, not a standalone MCP tool. Use the match’s input schema for the operation. The `body` argument distinguishes `state: missing` from `state: present` with a `value`; an empty object is a present value.

## Response guidance

Built-in tools put recovery advice in the result text. The same guidance is available as structured data in `_meta["computerlove.tech/umbod"]` (`schema_version: 1`), with the request ID and build. Connector tools do not carry it.

A failed call reports one of three outcomes: `not_started`, `unknown`, or `completed`. Never repeat a write whose outcome is `unknown` or `completed` unless the guidance says so. Two calls are safe to retry: upload completion with the same session ID, and `report_diagnostic` with identical data and the same key.
