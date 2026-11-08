# Admin MCP

The admin tools use a separate [MCP endpoint](../reference/endpoints-and-ports.md) on port `8013` by default and require membership in `config.authorization.adminGroup` via `config.authorization.adminMembershipClaim`. They configure existing `native`, `openapi`, and `downstream_mcp` connectors; they do not create or publish connectors.

## Hosting and deployment

`AppConfig.mcp_administrator` selects `shared` or `separate` hosting independently of `UMBOD_FEATURE_MCP_ADMINISTRATOR_ENABLED`. Disabling that feature removes administrator tools and prevents the separate listener from starting; it does not disable ordinary MCP tools. Separate hosting moves administrator tools off the ordinary MCP endpoint. Both listeners run inside `umbod mcp serve`, never inside the API process. Authentication and administrator membership checks still apply; a private bind or Service is not authorization.

For source deployments, `UMBOD_MCP_ADMINISTRATOR_HOSTING` defaults to `separate`, `UMBOD_MCP_ADMINISTRATOR_HOST` to `127.0.0.1`, `UMBOD_MCP_ADMINISTRATOR_PORT` to `8013`, and `UMBOD_MCP_ADMINISTRATOR_BASE_URL` to `http://localhost:8013`. The base URL is the client-visible administrator server base, not the bind address; clients append `/mcp`. For OIDC, allow the administrator origin's `/auth/callback` URL in the upstream identity provider alongside the ordinary MCP callback; switching to separate hosting introduces a distinct callback origin. Set `UMBOD_MCP_ADMINISTRATOR_HOSTING=shared` to register administrator tools on the ordinary MCP endpoint without an additional listener. Direct single-ASGI embedding requires explicit shared hosting; `umbod mcp serve` supervises separate listeners.

For Helm, `core.mcp.administrator.hosting=separate` and `config.features.mcp.administratorEnabled=true` are the defaults. Select `core.mcp.administrator.hosting=shared` to opt into shared hosting. Set `core.mcp.administrator.port` (default `8013`) and `core.mcp.administrator.baseUrl` (default `http://localhost:8013`) for the intended private clients. An active separate listener requires an absolute origin without credentials, a path, query, or fragment; an optional root slash is allowed. HTTPS is required outside loopback. Dedicated port-range and origin checks do not apply while hosting is shared or administrator tools are disabled. Helm binds the listener to `0.0.0.0` inside the MCP container so its private ClusterIP Service can reach it. With release name `umbod`, use `kubectl port-forward service/umbod-mcp-administrator 8013:8013` for local access at `http://localhost:8013/mcp`. Adjust both port numbers for a custom listener port. No administrator ingress is installed. Use typed chart settings rather than overriding managed administrator or feature environment variables through `core.api.env` or `core.mcp.env`. The chart rejects active administrator port collisions with API, MCP, metrics, and enabled telemetry listeners.

For Compose, the base file selects separate hosting, propagates settings to API and MCP for inspection and validation, and hosts the listener only in `mcp`. It binds inside that container to `0.0.0.0:8013` and publishes only `127.0.0.1:8013`; ordinary MCP remains on `8011`. Set `UMBOD_MCP_ADMINISTRATOR_BASE_URL` when private clients use another address. Do not publish this port through Traefik or a public ingress. From `umbod/`, opt into shared hosting with `docker compose -f docker-compose.yml -f docker-compose.mcp-shared.yml up -d --force-recreate api mcp`; that override removes the administrator port publication. The override requires Docker Compose 2.24.4 or newer. Return to separate hosting with `docker compose -f docker-compose.yml up -d --force-recreate api mcp`. Supply the persistent `UMBOD_ROOT_SECRET` required by both servers before starting Compose.

## Tools

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
