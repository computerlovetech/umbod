# Endpoints and ports

## Local access

After installing Umbod with the local Helm profile, forward the frontend Service:

```bash
kubectl port-forward service/umbod-frontend 3000:3000
```

Open the administration interface at [http://localhost:3000](http://localhost:3000).

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

Set `ingress.host`, `ingress.className`, annotations, and TLS values for the target cluster. Set `config.publicOrigins.site`, `config.publicOrigins.api`, and `config.publicOrigins.mcp` to the corresponding browser- and client-visible origins.
