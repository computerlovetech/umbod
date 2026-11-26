# Connect to Umbod

Expose the workspace, REST API, and ordinary MCP endpoint. Keep administrator MCP, telemetry collection, and metrics private. For local access, follow the [installation guide’s port-forwards](../getting-started/kubernetes-installation.md).

| Feature | Default Helm service port | Routing |
| --- | ---: | --- |
| Workspace | `3000` | Public `/` |
| REST API | `8000` | Public `/api`; retain the prefix |
| Ordinary MCP | `8011` | Public `/mcp` |
| Administrator MCP | `8013` | Private by default; see [administrator setup](configuration.md#administrator-mcp-hosting) |
| OTLP collector | `4318` | Private and opt-in; see [telemetry collection](telemetry-ingestion.md) |

With Ingress, configure TLS and set the [public origins](configuration.md#public-origins) to the addresses clients use. Ordinary MCP is available locally at `http://localhost:8011/mcp` after forwarding `service/umbod-mcp`. Do not route `/v1/*` or the Prometheus ports (`8001`, `8012`) through public Ingress.

API and MCP share one core Pod and data volume. The workspace runs separately. Enable [persistence](configuration.md#persistence) to retain data across core Pod replacement. Keep API and MCP on the same file-content storage, whether local or [S3](s3-file-storage.md).

## Administration API clients

Shared installations supply a same-origin authentication gateway for browser sign-in; the chart does not install one. Forward verifiable credentials and preserve `Origin` and cookies. Cookie-authenticated writes require a trusted `Origin` and `X-Umbod-Web-Request: 1`. Return API auth failures as API responses instead of redirecting to login HTML. Keep MCP OAuth discovery reachable independently of the browser login gateway.

Native clients send bearer credentials and use `/api/admin`, not `/admin`. Tokens must meet the configured issuer, audience, and membership requirements. Use `/api/admin/openapi.json` for the administrator API contract and `/api/me/profile` for the signed-in identity and capabilities. For local Compose development, the workspace is available on port `3010` without the `auth` profile.
