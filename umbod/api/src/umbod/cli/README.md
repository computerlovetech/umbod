# CLI

**Module responsibility:** Typer commands for running the Umbod REST API and MCP services, inspecting configuration, and explicit trusted operator filesystem bootstrap.

**Read when working with:** Command-line arguments, service startup commands, configuration validation, or terminal output.

## Service composition

REST targets `umbod.hosting.rest_service:create_app` with the Uvicorn factory flag. MCP targets `umbod.hosting.mcp_service:app`. Both use the backend-owned [hosting API](../hosting/README.md); server commands preflight the required nonblank `UMBOD_ROOT_SECRET` before logging or Uvicorn, including reload-parent socket binding. Failure reports a variable-naming error on stderr and exits nonzero. Configuration inspection commands retain generic loader semantics.

## Modules

### `api.py`

**Read when working with:** Commands that start or manage the API service.

### `config.py`

**Read when working with:** Commands that validate or display resolved configuration.

### `umbod_sdk.connectors.py`

**Read when working with:** Deployment-time validation of connector plugin entry points, SDK compatibility, and structural definitions.

### `mcp.py`

**Read when working with:** Commands that start or manage the MCP service.

### `filesystem/`

**Read when working with:** Explicit operator-only root bootstrap. `command.py` registers `umbod filesystem bootstrap --policy-file PATH`; `ports.py` defines the policy input contract, `policy.py` reads and validates JSON, and `service.py` prepares the configured persistence runtime, invokes core provisioning, and always shuts the runtime down.

The policy file is required and validated before persistence is opened. Its required `grants` array contains entries with required `principal` and `permissions` fields. Each principal requires `type` (`user` or `group`), `issuer`, and `id`. Permissions are `discover`, `read`, `write`, `delete`, or `share`. Empty grants are valid. Extra fields, including owner and recursive fields, are rejected. Core owns all bootstrap policy decisions; grants are root-direct and nonrecursive.

This trusted command uses the existing `.env` and environment configuration loader and public configured persistence provider. Run it against the intended service configuration and database before delivery requests. Containers expose the same executable invocation. An explicitly supplied `--policy-file /dev/stdin` supports trusted operator input through `kubectl exec -i`. No server startup or delivery request invokes bootstrap.

Bootstrap does not reconcile existing grants: replay leaves revoked grants revoked and ignores newly supplied grants or changed permissions. Conflicts require operator inspection and explicit migration or recovery, never automatic adoption. Output does not expose policy contents, principal identities, paths, or underlying errors.

### `main.py`

**Read when working with:** CLI registration and the executable entrypoint.
