# CLI

**Module responsibility:** Typer commands for running the Umbod REST API and MCP services and inspecting configuration.

**Read when working with:** Command-line arguments, service startup commands, configuration validation, or terminal output.

## Modules

### `api.py`

**Read when working with:** Commands that start or manage the API service.

### `config.py`

**Read when working with:** Commands that validate or display resolved configuration.

### `umbod_sdk.connectors.py`

**Read when working with:** Deployment-time validation of connector plugin entry points, SDK compatibility, and structural definitions.

### `mcp.py`

**Read when working with:** Commands that start or manage the MCP service.

### `main.py`

**Read when working with:** CLI registration and the executable entrypoint.
