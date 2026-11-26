# Admin MCP

Keep the administrator tools on the default private [MCP endpoint](endpoints-and-ports.md) on port `8013`. Set `config.authorization.adminGroup` to the required group and `config.authorization.adminMembershipClaim` to the claim that carries membership. Private networking does not replace sign-in and membership checks.

Use these tools to find administration targets, configure existing connectors, manage group grants, and administer shared filesystem namespaces. They cannot create or publish connectors.

## Hosting and deployment

Choose `separate` to keep administrator tools off the ordinary MCP endpoint, or explicitly choose `shared` to serve them there without a second listener. `AppConfig.mcp_administrator` selects the hosting mode independently of `UMBOD_FEATURE_MCP_ADMINISTRATOR_ENABLED`. If you do not need administrator tools, disable the feature: this also prevents the separate listener from starting, without disabling ordinary MCP tools. Both listeners belong to `umbod mcp serve`, never the API process.

**Helm.** With release name `umbod`, run `kubectl port-forward service/umbod-mcp-administrator 8013:8013` for local access at `http://localhost:8013/mcp`. Adjust both port numbers for a custom listener port. The chart binds to `0.0.0.0` inside the MCP container so the private ClusterIP Service can reach it. It does not install administrator ingress.

The defaults are `core.mcp.administrator.hosting=separate` and `config.features.mcp.administratorEnabled=true`. For shared hosting, set `core.mcp.administrator.hosting=shared`. For separate hosting, set `core.mcp.administrator.port` (default `8013`) and `core.mcp.administrator.baseUrl` (default `http://localhost:8013`) to suit private clients. Use an absolute origin with no credentials, path, query, or fragment; a root slash is allowed. Use HTTPS outside loopback. The chart rejects port collisions with API, MCP, metrics, and enabled telemetry listeners. The dedicated port-range and origin checks apply only when the separate listener is active. Use these chart settings rather than overriding administrator or feature environment variables through `core.api.env` or `core.mcp.env`.

**Compose.** Supply the persistent `UMBOD_ROOT_SECRET` required by both servers before starting Compose. The base file selects separate hosting and gives both API and MCP the settings for inspection and validation, but only `mcp` runs the listener. It binds to `0.0.0.0:8013` inside the container and publishes only `127.0.0.1:8013`. Ordinary MCP remains on `8011`. Set `UMBOD_MCP_ADMINISTRATOR_BASE_URL` when private clients use another address. Do not publish this port through Traefik or a public ingress. From `umbod/`, opt into shared hosting with `docker compose -f docker-compose.yml -f docker-compose.mcp-shared.yml up -d --force-recreate api mcp`; that override removes the administrator port publication. The override requires Docker Compose 2.24.4 or newer. Return to separate hosting with `docker compose -f docker-compose.yml up -d --force-recreate api mcp`.

**Source deployments.** `UMBOD_MCP_ADMINISTRATOR_HOSTING` defaults to `separate`, `UMBOD_MCP_ADMINISTRATOR_HOST` to `127.0.0.1`, `UMBOD_MCP_ADMINISTRATOR_PORT` to `8013`, and `UMBOD_MCP_ADMINISTRATOR_BASE_URL` to `http://localhost:8013`. The base URL is the client-visible administrator server base, not the bind address; clients append `/mcp`. For OIDC, register the administrator origin's `/auth/callback` URL in the upstream identity provider alongside the ordinary MCP callback; switching to separate hosting introduces a distinct callback origin. Set `UMBOD_MCP_ADMINISTRATOR_HOSTING=shared` to register administrator tools on the ordinary MCP endpoint without an additional listener. Direct single-ASGI embedding requires explicit shared hosting; `umbod mcp serve` supervises separate listeners.

## Tools

See the [built-in tool reference](../reference/built-in-tools.md#administrator-tools) for operation inputs and outputs.
