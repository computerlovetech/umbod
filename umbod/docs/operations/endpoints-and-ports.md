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
| `umbod-telemetry` (when `telemetry.enabled=true`) | 4318 |
| `umbod-mcp-administrator` (administrator enabled and separate hosting) | 8013 |

The optional telemetry Service targets the private collector listener in the existing API container, not a separate Deployment. Docker Compose forwards this listener only on `127.0.0.1:14318` to container port `4318`; public REST remains on host port `18010`.

The administrator Service is enabled by default and targets the MCP process, never API. It has no public ingress. Explicit shared hosting creates no administrator listener or Service. Compose publishes the default administrator port only on `127.0.0.1:8013`; its shared-hosting override removes that publication. See [administrator MCP deployment](../operations/admin-mcp.md#hosting-and-deployment) for settings and exact commands.

The core Pod also declares API metrics port `8001` and MCP metrics port `8012`. These metrics ports are internal workload ports and are not exposed by the chart's Services.

## Ingress routing

When `ingress.enabled=true`, the chart routes three configurable paths:

| Helm value | Default path | Destination |
| --- | --- | --- |
| `ingress.paths.frontend` | `/` | Frontend Service |
| `ingress.paths.api` | `/api` | API Service |
| `ingress.paths.mcp` | `/mcp` | MCP Service |

The `/api` prefix is retained: administration requests reach `/api/admin`, not `/admin` through an Ingress rewrite. The frontend SPA uses this same-origin address by default. Local frontend Service port-forwards proxy `/api` to the API Service.

The chart never adds a public `/v1` ingestion route. Public REST excludes `/v1/*` and `/api/v1/*`. When `telemetry.enabled=true`, authenticated OTLP HTTP JSON and protobuf logs, metrics, and traces use the private collector ClusterIP Service. `telemetry.port` and `telemetry.servicePort` independently configure its listener and Service ports. See [telemetry ingestion](telemetry-ingestion.md) for authentication, limits, and client compatibility.

Set `ingress.host`, `ingress.className`, annotations, and TLS values for the target cluster. Set `config.publicOrigins.site`, `config.publicOrigins.api`, and `config.publicOrigins.mcp` to the corresponding browser- and client-visible origins.

## Administration API clients

- `/api/me/profile` returns authenticated identity under `user` and effective UI permissions under `capabilities`, for both ordinary users and administrators.
- `capabilities.administration` controls administration entry points; identity display does not require administration access.
- `/api/admin/users` is retired; authenticated administrator requests receive 404.
- `/api/admin/openapi.json` provides the authenticated administration OpenAPI contract.
- `/api/admin/connectors/catalog`, `/api/admin/connectors/openapi`, `/api/admin/connectors/mcp`, and `/api/admin/mcp-permissions` expose the shared administration resources.
- `POST /api/admin/connectors/openapi/setup` creates, imports, and configures an OpenAPI connector in one backend operation, with compensation on failure rather than a guaranteed database transaction.
- Administration API requests use `/api/admin` only; legacy `/admin` API requests return 404. Private system runtime endpoints are not part of the public client API.

Native clients send bearer credentials in `Authorization`. Production tokens must satisfy configured issuer, audience, and administrator membership requirements. Obtaining tokens and implementing native login remain client responsibilities.

The website can use same-origin gateway-managed sessions. The gateway must forward verifiable credentials to Python, retain the original cookie and Origin headers, and return API authentication failures without a login-page redirect. Cookie-bearing writes require `X-Umbod-Web-Request: 1` and a trusted Origin. Cross-origin cookie authentication is not enabled; CORS supports configured browser origins using bearer credentials.

The frontend's `/system/health` checks static hosting only, not backend availability. `/app-config.json` supplies public runtime addresses and is not a secret store.
