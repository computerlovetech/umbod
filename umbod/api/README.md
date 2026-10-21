# Umbod API

Minimal FastAPI, FastMCP, and Typer scaffold for Umbod.

## Hosting boundary

[`umbod.hosting`](src/umbod/hosting/README.md) is the supported Python application-composition API. Desktop embeds its REST and MCP applications in one process; Kubernetes runs separate REST and MCP services through the same API. Its contract documents supported injections, resource ownership, compatibility checks, and remaining HTTP and persistence coupling.

## Telemetry ingestion

The REST boundary exposes authenticated OTLP JSON logs, metrics, and traces under `/v1`. Accepted exports use the shared structured stdout logger with checked write acknowledgements; ingestion is disabled by default. See [telemetry ingestion](../docs/reference/telemetry-ingestion.md) for operator settings and deployment paths, and `src/umbod/rest/telemetry/README.md` for module responsibilities.

## Development

`.python-version` selects Python 3.14 for local and CI commands, matching the deployed image. The current locked dependency set is not yet compatible with Python 3.15.

```bash
uv sync
uv run umbod api serve --reload
uv run umbod mcp serve --reload
```
# Python distribution

This application is distributed as `umbod` (Python 3.14+). The public
`connectors` imports and discovery contract are provided by the
`umbod` workspace package. Bundled implementations are provided by
the `umbod-connectors` workspace package under `umbod_connectors`.
The core image contains `umbod` and the connector SDK only. Docker Compose
materializes the separately built plugin bundle into a named volume and mounts the
same volume read-only at `/plugins` in API and MCP with `PYTHONPATH=/plugins`.
The one-shot initializer clears the volume before copying the current bundle, so
removed plugin distributions cannot persist across deployments.

The core project keeps bundled connectors in its development dependency group for
tests and local development. Runtime groups remain plugin-free.

Build with `uv build --wheel`.
