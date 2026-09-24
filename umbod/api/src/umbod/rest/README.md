# REST

**Module responsibility:** FastAPI boundary for administration, system, authentication, and user-facing HTTP behavior.

**Read when working with:** Routes, HTTP schemas, authentication middleware, dependency providers, API metrics, or application startup.

## Entry modules

### `main.py`, `factories.py`, and `dependencies.py`

**Read when working with:** Application startup, REST composition, dependency lifetimes, or adapter wiring.

## Submodules

### `authentication/`

**Read when working with:** Administrative authentication, JWT handling, or local authentication simulation.

### `connectors/`

**Read when working with:** Connector administration HTTP surface shared across kinds, plus kind-specific packages under `native/`, `openapi/`, and `downstream_mcp/`.

Shared root modules: kind-agnostic DI, shared schemas, invocation policy helpers, tool activation, publication status, and capability-description response mapping.

Kind packages isolate kind-specific routes, schemas, and dependencies:

- `connectors/native/` — native catalog administration (`/connectors/catalog`)
- `connectors/openapi/` — OpenAPI connector administration and imports (`/connectors/openapi`)
- `connectors/downstream_mcp/` — Downstream MCP administration (`/connectors/mcp`)

Downstream MCP responses also describe saved `oauth` authorizations. Interactive
sign-in is currently a Local-only host extension (`umbod/oauth.py`), not an
Enterprise admin route. Shared runtime/storage support lives in
`core/connectors/downstream_mcp/adapters/oauth.py`; Enterprise account ownership
and multi-worker sign-in coordination remain undecided.

### `mcp_permissions/`

**Read when working with:** Group-to-tool permission APIs and permission events.

### `capability_descriptions/`

**Read when working with:** Capability description overrides exposed through the API.

### `instance_configuration/`

**Read when working with:** Resolved instance configuration exposed to clients.

### `metrics/`, `system/`, and `users/`

**Read when working with:** API observability, health endpoints, or current-user behavior.
