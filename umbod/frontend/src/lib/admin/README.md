# Admin

**Module responsibility:** Frontend administration domain, including typed API adapters, feature state, and transport composition.

**Read when working with:** Administration data flows, API payload schemas, connector management, permissions, OpenAPI integrations, or downstream MCP servers.

## Modules

### `*-api.ts`

**Read when working with:** Feature-specific API routes, Zod payload schemas, or mapping between transport data and frontend models.

### `*.svelte.ts`

**Read when working with:** Feature state and administration workflows.

## Submodules

### `overview/`

**Read when working with:** Administration dashboard counts, source availability, attention aggregation, or bounded tool activation loading. See `overview/README.md`.

### `infrastructure/`

**Read when working with:** Browser HTTP transport, validated public runtime configuration, authentication expiry, or composite API composition.

### `operations/`

**Read when working with:** Typed browser mutations grouped by connector, downstream MCP, OpenAPI, and permissions contexts; reusable submit callbacks, reconciliation, and pending cleanup. See `operations/README.md`.

### `*-browser-api.ts`

**Read when working with:** Browser detail composition through backend adapters, including cancellation and wire-to-UI mapping. These clients do not call frontend aggregation endpoints.

### `openapi-setup.ts`

**Read when working with:** The validated JSON setup request and cleanup-failure contract for backend-owned OpenAPI setup.
