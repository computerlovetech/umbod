# Umbod API

Minimal FastAPI, FastMCP, and Typer scaffold for Umbod.

## Development

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
