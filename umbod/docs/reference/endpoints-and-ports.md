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

Set `ingress.host`, `ingress.className`, annotations, and TLS values for the target cluster. Set `config.publicOrigins.site`, `config.publicOrigins.api`, and `config.publicOrigins.mcp` to the corresponding browser- and client-visible origins.
