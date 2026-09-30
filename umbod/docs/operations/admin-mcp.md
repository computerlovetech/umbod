# Admin MCP

The admin tools use the [MCP endpoint](../reference/endpoints-and-ports.md) and require membership in `config.authorization.adminGroup` via `config.authorization.adminMembershipClaim`. They configure existing `native`, `openapi`, and `downstream_mcp` connectors; they do not create or publish connectors.

| Tool | Inputs | Returns |
| --- | --- | --- |
| `read_connector_configuration` | `connector_kind`, `connector_id` | Capability activation, tool policies, description state, and group permissions. |
| `upsert_connector_configuration` | `connector_kind`, `connector_id`, `desired_state` | Updated configuration. |

`desired_state` contains an `operations` array:

| Operation | Fields | Purpose |
| --- | --- | --- |
| `set_capability_activation` | `capability_kind`, `capability_key`, `activation_status` | Enable or disable a capability. |
| `set_capability_invocation_policy` | `capability_kind`, `capability_key`, `mode`, `expected_revision` | Set a tool to `direct` or `ask`. |
| `set_capability_description` | `description`, `expected_revision` | Override the connector capability description. |
| `use_system_capability_description` | `expected_revision` | Restore the system description. |
| `update_group_permissions` | `group_id`, `connector_status`, `capabilities` | Change connector and/or capability grants for a group. |

Upserts are **partial**: omitted settings stay unchanged, and an empty `operations` array only reads the current state. Read first for capability keys and revisions; stale revisions or invalid targets reject the whole update. Activation alone does not grant group access. Invocation policies apply only to tools; activation and grants also support prompts, resources, and resource templates where available.
