# Core

**Module responsibility:** Application behavior, domain models, ports, and feature-local adapters shared by delivery boundaries.

**Read when working with:** Business rules, application workflows, domain models, ports, or feature-specific integration behavior used by REST and MCP.

## Submodules

### Shared concepts

### `administrator/connector_configuration/`

**Read when working with:** Shared administrator connector configuration models, explicit discriminated mutation operations, requests, results, reader and atomic mutation ports, or application service behavior. Import its public API only from `umbod.core.administrator.connector_configuration`.

### `activation/`

**Read when working with:** Capability activation state (tools, prompts, resources), enable/disable workflows, or activation persistence shared by connector kinds.

### `permissions/`

**Read when working with:** Group access, tool permissions, authorization state, or permission notifications.

### `invocation/`

**Read when working with:** Cross-kind invocation policy, approval nonces, gated tool execution, or invocation-policy events.

### `publishing/`

**Read when working with:** Connector publish/unpublish state, publication persistence, or publication events.

### `capabilities/`

**Read when working with:** Shared capability vocabulary (identity, catalog, availability), capability description overrides, or public tool naming/schemas.

### `configuration/`

**Read when working with:** Encrypted connector configuration, configuration secrets/ciphers, or configuration-changed events.

### `identity/`

**Read when working with:** Cross-kind connector ID uniqueness checks.

### Connector kinds

### `connectors/native/`

**Read when working with:** Native/built-in connector lifecycle, plugin registry, runtime assembly, or deployment availability.

### `connectors/openapi/`

**Read when working with:** OpenAPI imports, generated connector models, operation execution, or administrator-configurable OpenAPI state. `administrator_configuration.py` reads complete configurable state. `administrator_configuration_mutation.py` validates and atomically persists explicit mixed operations across activation, invocation policy, description override, and group permissions.

### `connectors/downstream_mcp/`

**Read when working with:** Registration, discovery, security, or invocation of downstream MCP servers.

### Other

### `messaging/`

**Read when working with:** Core messaging contracts shared with transport implementations.

### `persistence/`

**Read when working with:** Persistence ports, queries, or database readiness behavior.

**Dependency rule:** Shared root packages never import `umbod_sdk.connectors.native`, `umbod_sdk.connectors.openapi`, or `umbod_sdk.connectors.downstream_mcp`. Kind packages and delivery boundaries may import shared roots. Kind-stitching composition belongs in delivery wiring (for example REST).
