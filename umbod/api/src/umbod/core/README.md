# Core

**Module responsibility:** Application behavior, domain models, ports, and feature-local adapters shared by delivery boundaries.

**Read when working with:** Business rules, application workflows, domain models, ports, or feature-specific integration behavior used by REST and MCP.

## Submodules

### Shared concepts

### `administrator/connector_configuration/`

**Read when working with:** Shared administrator connector configuration models, explicit discriminated mutation operations, requests, results, reader and atomic mutation ports, or application service behavior. Import its public API only from `umbod.core.administrator.connector_configuration`. `reader.py` reads complete cross-kind configurable state. `mutation.py` validates and atomically persists mixed activation, invocation policy, description override, and permission operations with their durable events. `catalog.py` defines the connector inventory port.

### `activation/`

**Read when working with:** Capability activation state (tools, prompts, resources), enable/disable workflows, or activation persistence shared by connector kinds.

### `permissions/`

**Read when working with:** Group access, tool permissions, authorization state, or permission notifications. `stores/service.py` exposes session-bound permission reads and updates for atomic configuration writes.

### `invocation/`

**Read when working with:** Cross-kind invocation policy, approval nonces, gated tool execution, or invocation-policy events.

### `publishing/`

**Read when working with:** Connector publish/unpublish state, publication persistence, or publication events.

### `virtual_filesystem/`

**Read when working with:** Standalone filesystem models, namespace/content ports, driver-provided shared root discovery, nested node creation, and streamed content publication. The [local index](virtual_filesystem/README.md) describes the initial acceptance slice and deferred behavior. No REST/MCP or authorization wiring is included.

### `user_catalogue/`

**Read when working with:** Safe authenticated-user catalogue models, source/reader ports, in-memory acceptance and explicit shared capability-grant filtering. The [local index](user_catalogue/README.md) describes request-scoped projection responsibilities.

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

**Read when working with:** OpenAPI imports, generated connector models, operation execution, or administrator-configurable OpenAPI inventory. `administrator_catalog.py` adapts persisted operation summaries to the shared configuration catalog port. `management/setup_ports.py` defines the client-independent setup contract and explicit failure states; `management/setup.py` validates, creates, imports, and configures a connector, compensating configuration and connector persistence on failure. Setup is a backend operation, not a browser workflow or a guaranteed database transaction.

### `connectors/downstream_mcp/`

**Read when working with:** Registration, discovery, security, or invocation of downstream MCP servers. `oauth/` owns shared sign-in orchestration, metadata discovery, registration decisions, scope summaries, diagnostics, safe failures, and authorization/discovery status. `oauth/ports.py` defines deployment storage and callback ports; `oauth/provider.py` applies public-client policy for both interactive and runtime use. `adapters/fastmcp/oauth_client.py` contains the SDK session transport. Shared OAuth policy remains independent of deployment-specific hosts.

`personal_connections/` owns canonical principal keys, personal enablement, opaque authorization states, revision-checked writes, a principal-provider port and the pure verified-claims identity policy in `principal.py`. Its [index](connectors/downstream_mcp/personal_connections/README.md) describes the public contracts. `stores/personal_connections.py` persists encrypted principal-bound records in an additive table; connector aggregate deletion removes them transactionally. OAuth definitions without `authorization_mode` remain shared. The [downstream index](connectors/downstream_mcp/README.md) describes discovery-free personal creation, publication and connector-grant assignment. `personal_connections/inventory.py` coordinates eligible personal selection and cleanup; production storage binds mutations to an existing personal definition transactionally. Shared discovery/OAuth/execution paths still reject personal mode. Durable personal sign-in uses independently resolved attempt/provider policy, defaulting available when secure prerequisites are configured, encrypted attempt storage and worker-independent callbacks; authorization never enables execution. See the [foundation specification](../../../../docs/operations/personal-downstream-mcp-oauth-specification.md), [catalogue iteration](../../../../docs/operations/personal-downstream-mcp-catalogue-specification.md) and [authorization iteration](../../../../docs/operations/personal-downstream-mcp-authorization-specification.md).

### Other

### `messaging/`

**Read when working with:** Core messaging contracts shared with transport implementations. `stores/event_stream.py` provides durable stream storage and `append_event_in_session` for atomic state-and-event writes.

### `telemetry/`

**Read when working with:** Validated telemetry exports, sink ports, in-memory acceptance, or existing stdout logger integration.

### `persistence/`

**Read when working with:** Persistence ports, queries, or database readiness behavior.

**Dependency rule:** Shared root packages never import `umbod_sdk.connectors.native`, `umbod_sdk.connectors.openapi`, or `umbod_sdk.connectors.downstream_mcp`. Kind packages and delivery boundaries may import shared roots. Kind-stitching composition belongs in delivery wiring (for example REST).
