# Endpoints and ports

## Local access

After installing Umbod with the local Helm profile and setting `config.publicOrigins.mcp=http://localhost:8011`, forward the frontend and MCP Services in separate terminals:

```bash
kubectl port-forward service/umbod-frontend 3000:3000
```

```bash
kubectl port-forward service/umbod-mcp 8011:8011
```

Open the administration interface at [http://localhost:3000](http://localhost:3000). A desktop agent on the same computer can use the remote HTTP MCP endpoint `http://localhost:8011/mcp`. Keep both forwards running while connected. See the [Kubernetes installation guide](../getting-started/kubernetes-installation.md) for the local install command.

## Kubernetes service ports

| Service | Application port |
| --- | ---: |
| `umbod-frontend` | 3000 |
| `umbod-api` | 8000 |
| `umbod-mcp` | 8011 |

The core Pod also declares API metrics port `8001` and MCP metrics port `8012`. These metrics ports are internal workload ports and are not exposed by the chart's Services.

## Ingress routing

When `ingress.enabled=true`, the chart routes three configurable paths:

| Helm value | Default path | Destination |
| --- | --- | --- |
| `ingress.paths.frontend` | `/` | Frontend Service |
| `ingress.paths.api` | `/api` | API Service |
| `ingress.paths.mcp` | `/mcp` | MCP Service |

The `/api` prefix is retained: administration requests reach `/api/admin`, not `/admin` through an Ingress rewrite. The frontend SPA uses this same-origin address by default. Local frontend Service port-forwards proxy `/api` to the API Service.

The chart additionally routes `/v1` unchanged to the API Service for OTLP JSON logs, metrics, and traces. `/api/v1/*` is not rewritten to the receiver. See [telemetry ingestion](telemetry-ingestion.md) for authentication, limits, and client compatibility.

Set `ingress.host`, `ingress.className`, annotations, and TLS values for the target cluster. Set `config.publicOrigins.site`, `config.publicOrigins.api`, and `config.publicOrigins.mcp` to the corresponding browser- and client-visible origins.

## Administration API clients

- `/api/admin/users` resolves the authenticated identity.
- `/api/admin/openapi.json` provides the authenticated administration OpenAPI contract.
- `/api/admin/connectors/catalog`, `/api/admin/connectors/openapi`, `/api/admin/connectors/mcp`, and `/api/admin/mcp-permissions` expose the shared administration resources.
- `POST /api/admin/connectors/openapi/setup` creates, imports, and configures an OpenAPI connector in one backend operation, with compensation on failure rather than a guaranteed database transaction.
- Administration API requests use `/api/admin` only; legacy `/admin` API requests return 404. Private system runtime endpoints are not part of the public client API.

Native clients send bearer credentials in `Authorization`. Production tokens must satisfy configured issuer, audience, and administrator membership requirements. Obtaining tokens and implementing native login remain client responsibilities.

The website can use same-origin gateway-managed sessions. The gateway must forward verifiable credentials to Python, retain the original cookie and Origin headers, and return API authentication failures without a login-page redirect. Cookie-bearing writes require `X-Umbod-Web-Request: 1` and a trusted Origin. Cross-origin cookie authentication is not enabled; CORS supports configured browser origins using bearer credentials.

The frontend's `/system/health` checks static hosting only, not backend availability. `/app-config.json` supplies public runtime addresses and is not a secret store.
