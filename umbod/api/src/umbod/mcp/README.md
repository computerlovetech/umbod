# MCP

**Module responsibility:** FastMCP boundary for capability discovery, tool publication and execution, authentication, and protocol behavior.

**Read when working with:** MCP server setup, tool exposure, tool invocation, protocol middleware, authentication, or MCP observability.

## Entry modules

### `main.py` and `public_app.py`

**Read when working with:** MCP process startup, server construction, or the public MCP application.

### `context.py` and `settings.py`

**Read when working with:** MCP runtime dependencies, context, or process settings.

### `administrator/`

**Read when working with:** Administrator-only MCP capabilities. `connector_configuration.py` registers connector configuration tools, `tools.py` contains their implementations, and `authorization.py` and `principal.py` adapt access-token claims. The upsert tool keeps the `desired_state` argument and accepts `{operations: [...]}` with explicit discriminated operations. Shared models and orchestration live in `umbod.core.administrator.connector_configuration`.

## Submodules

### `connectors/`

**Read when working with:** Native connector tool registration, exposure modes, approval, invocation, or direct request-lifetime file input apps.

File-input connector tools keep uploaded bytes only for the current app-backend invocation. Policy and approval receive only filename, media type, size, and SHA-256 metadata. Approval-required invocations cannot be resumed because no upload storage exists; callers must submit the file again after approval. File-input connector tools currently support only flat exposure; gateway and codemode registration reject them.

### `downstream_mcp_connectors/`

**Read when working with:** Downstream discovery, reconciliation, publication, or invocation.

### `openapi_connectors/`

**Read when working with:** MCP exposure and execution of OpenAPI-generated operations.

### `auth/`

**Read when working with:** MCP OAuth, client storage, authorization, or consent.

### `messaging/`

**Read when working with:** Event transport and state synchronization used by the MCP process.

### `logging/`, `metrics/`, `middleware/`, and `tools/`

**Read when working with:** Audit behavior, instrumentation, protocol request handling, or observed registration of internal FastMCP tools. `tools/registration.py` preserves callable-derived FastMCP metadata while observing the complete `FunctionTool.run` lifecycle; `tools/invocation/` contains shared invocation lifecycle and telemetry behavior.
