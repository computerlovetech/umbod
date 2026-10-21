# MCP

**Module responsibility:** FastMCP boundary for capability discovery, tool publication and execution, authentication, and protocol behavior.

**Read when working with:** MCP server setup, tool exposure, tool invocation, protocol middleware, authentication, or MCP observability.

## Entry modules

### `main.py` and `public_app.py`

**Read when working with:** MCP process startup, server construction, or the public MCP application.

### `context.py` and `settings.py`

**Read when working with:** MCP runtime dependencies, context, or process settings.

### `administrator/`

**Read when working with:** Administrator-only MCP capabilities. `connector_configuration.py` registers connector configuration tools, `tools.py` contains their implementations, and `authorization.py` and `principal.py` adapt access-token claims. The upsert tool keeps the `desired_state` argument and accepts `{operations: [...]}` with explicit discriminated operations. Shared models, catalog port, and orchestration live in `umbod.core.administrator.connector_configuration`. Both tools support existing native, OpenAPI, and downstream MCP connectors. `administrator/catalog.py` dispatches to each kind's registry or stored catalog without filtering disabled capabilities. The shared catalog reader and transactional mutation live in `core/administrator/connector_configuration/reader.py` and `mutation.py`; inventory lookups are scoped to the requested connector; activation and grants support all catalog capability kinds, while policies remain tool-only. Configuration writes atomically append REST-equivalent durable change events only for changed targets. Native administration includes unavailable registered definitions without changing runtime catalog filtering.

### `agent_instructions.py`

Registers the shared read-only `umbod://setup/agent-instructions` resource for Desktop and Enterprise. Copyable prompts in both setup views direct agents here to install idempotent user-scoped routing guidance with their own local file tools. The guidance covers flat, gateway, and code exposure modes, requires Umbod for connected-app access unless the user explicitly authorizes another method, and describes bounded recovery without automatic fallback. It remains independent of the connected-app catalog. This is a resource, not an MCP prompt or setup tool.

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

`auth/factory.py` leaves the Google, Entra, and Auth0 OAuth proxy issuer at FastMCP's public MCP base URL default. MCP resource metadata advertises Umbod's authorization server, and authorization metadata exposes Umbod's authorize, token, and register endpoints. Shared `oidc.issuer_url` remains the upstream token issuer for REST validation; Auth0 discovery independently supplies the upstream MCP token verifier's issuer.

### `messaging/`

**Read when working with:** Event transport and state synchronization used by the MCP process.

### `logging/`, `metrics/`, `middleware/`, and `tools/`

**Read when working with:** Audit behavior, instrumentation, protocol request handling, or observed registration of internal FastMCP tools. `tools/registration.py` preserves callable-derived FastMCP metadata while observing the complete `FunctionTool.run` lifecycle; `tools/invocation/` contains shared invocation lifecycle and telemetry behavior.

## Embedded host composition

Supported hosts use [`umbod.hosting`](../hosting/README.md) and `create_mcp_app`; `PublicAppConfig` and runtime contexts remain backend internals. `main.py` delegates to `umbod.hosting.mcp_service:app`, the separate service bootstrap.

The `invocation_log_sink` hook on `create_mcp_app` supplies a deployment-owned completed-invocation sink; the normal structured logger remains the default. `live_permission_updates.py` reads group permissions from the shared database when SQL messaging is selected, or the system HTTP API for HTTP messaging. This allows embedded REST/MCP applications to synchronize permissions without exposing an unauthenticated internal API.
