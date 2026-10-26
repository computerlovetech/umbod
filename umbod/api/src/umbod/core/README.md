# Core

**Module responsibility:** Application behavior, domain models, ports, and feature-local adapters shared by delivery boundaries.

**Read when working with:** Business rules, application workflows, domain models, ports, or feature-specific integration behavior used by REST and MCP.

## Submodules

### Shared concepts

### `callers/`

**Read when working with:** Transport-neutral caller observations, explicit authentication provenance, subject/issuer availability, separate unqualified `GroupMembership` observations and captured caller values shared by REST and MCP. Generic caller-provider wrappers are removed; feature-specific deferred capture remains at delivery boundaries only where operation freshness requires it. The [local index](callers/README.md) distinguishes caller facts from canonical ownership, group projections and authorization policy.

### `administrator/connector_configuration/`

**Read when working with:** Shared administrator connector configuration models, explicit discriminated mutation operations, requests, results, reader and atomic mutation ports, or application service behavior. Import its public API only from `umbod.core.administrator.connector_configuration`. `reader.py` reads complete cross-kind configurable state. `mutation.py` validates and atomically persists mixed activation, invocation policy, description override, and permission operations with their durable events. `catalog.py` defines the connector inventory port.

### `activation/`

**Read when working with:** Capability activation state (tools, prompts, resources), enable/disable workflows, or activation persistence shared by connector kinds.

### `permissions/`

**Read when working with:** Group access, tool permissions, authorization state, or permission notifications. `stores/service.py` exposes session-bound permission reads and updates for atomic configuration writes. `runtime.py` evaluates typed `GroupMembership` through `RuntimeGroupPermissions`, without parsing claims. Legacy constructor claim selectors remain adapter metadata for hosting compatibility. FastMCP callbacks and policy-specific claim capture live in `umbod.mcp.authorization` and `umbod.mcp.auth.groups`.

### `signals/`

**Read when working with:** Typed, application-scoped synchronous signals, explicit receiver registration, isolated ordinary receiver failures, or in-memory failure capture. Signals have no logging, metrics, transport, or global registration dependency. See [the local index](signals/README.md).

### `invocation/`

**Read when working with:** Cross-kind invocation policy, approval nonces, gated tool execution, or invocation-policy events. `failure_evidence.py` captures bounded exception types and traceback frames without messages, source lines or locals, with explicit internal, connector, downstream OpenAPI and downstream MCP origins. `tools/execution.py` scopes this evidence to each pipeline execution, restoring enclosing context on completion or cancellation.

### `publishing/`

**Read when working with:** Connector publish/unpublish state, publication persistence, or publication events.

### `filesystem/`

**Read when working with:** Filesystem models, namespace/content/access-control ports, shared namespace rules, root discovery, nested creation, streamed content publication, and persisted ownership/sharing. `stores/` owns typed table declarations and database-neutral namespace/policy stores over the shared Database port, following ADR-001. Concrete persistence drivers, byte-storage adapters, configuration, and factories remain infrastructure responsibilities under ADR-006; callers compose through the public `umbod.infrastructure` API. The [local index](filesystem/README.md) describes contracts and deferred behavior. `authorization/` supplies shared direct-node decisions through injected identity, namespace, and policy ports; `browsing/` supplies opt-in caller-aware DISCOVER summaries and parent-authorized, independently filtered child listing without content dependencies. All summary metadata attributes are DISCOVER-visible; observations are not atomic check/use. Production identity mapping, content/mutation enforcement, and delivery wiring remain deferred. No filesystem REST/MCP or authorization wiring is included.

### `user_catalogue/`

**Read when working with:** Safe authenticated-user catalogue models, source/reader ports, in-memory acceptance and explicit shared capability-grant filtering. The [local index](user_catalogue/README.md) describes request-scoped projection responsibilities.

### `capabilities/`

**Read when working with:** Shared capability vocabulary (identity, catalog, availability), capability description overrides, or public tool naming/schemas.

### `configuration/`

**Read when working with:** Encrypted connector configuration, configuration secrets/ciphers, or configuration-changed events.

### `network/`

**Read when working with:** Shared public-address validation, DNS-pinned `httpcore` adapters and pool configuration used by favicon and personal OAuth adapters. `network/adapters.py` owns these low-level primitives; feature-specific URL, authentication, redirect and deadline policies remain in their adapters. Public imports come from `umbod.core.network`.

### `icons/`

**Read when working with:** Shared favicon discovery for MCP and OpenAPI connectors. The [local index](icons/README.md) covers configurable ordered/concurrent strategy batches, explicit outcomes, bounded public HTTP fetching and credential-free website fallbacks.

### `identity/`

**Read when working with:** Cross-kind connector ID uniqueness checks.

### Connector kinds

### `connectors/native/`

**Read when working with:** Native/built-in connector lifecycle, plugin registry, runtime assembly, or deployment availability.

### `connectors/openapi/`

**Read when working with:** OpenAPI imports, generated connector models, operation execution, or administrator-configurable OpenAPI inventory. `administrator_catalog.py` adapts persisted operation summaries to the shared configuration catalog port. `management/setup_ports.py` defines the client-independent setup contract and explicit failure states; `management/setup.py` validates, creates, imports, and configures a connector, compensating configuration and connector persistence on failure. Setup is a backend operation, not a browser workflow or a guaranteed database transaction.

### `connectors/downstream_mcp/`

**Read when working with:** Registration, discovery, security, or invocation of downstream MCP servers. `oauth/` owns shared sign-in orchestration, metadata discovery, registration decisions, scope summaries, diagnostics, safe failures, and authorization/discovery status. `oauth/ports.py` defines deployment storage and callback ports; `oauth/provider.py` applies public-client policy for both interactive and runtime use. `adapters/fastmcp/oauth_client.py` contains the SDK session transport. Shared OAuth policy remains independent of deployment-specific hosts.

`personal_connections/` owns canonical principal keys, personal enablement, opaque authorization states, revision-checked writes, captured `PersonalCaller` values and the pure typed identity resolver in `principal.py`. Connection, OAuth, refresh and tool runtime services receive immutable operation inputs, not caller lookup callbacks. The feature-specific deferred caller port is consumed by the MCP runtime adapter, which constructs a core service per operation. `identity_models.py` and `identity_ports.py` distinguish observed facts from resolved canonical identity; `adapters/settings.py` and `adapters/identity.py` translate deployment configuration and accepted claims outside the policy. Its [index](connectors/downstream_mcp/personal_connections/README.md) describes the public contracts. `stores/personal_connections.py` persists encrypted principal-bound records in an additive table; connector aggregate deletion removes them transactionally. OAuth definitions without `authorization_mode` remain shared. The [downstream index](connectors/downstream_mcp/README.md) describes discovery-free personal creation, publication and connector-grant assignment. `personal_connections/inventory.py` coordinates eligible personal selection and cleanup; production storage binds mutations to an existing personal definition transactionally. Shared discovery/OAuth/execution paths still reject personal mode. Durable personal sign-in uses independently resolved attempt/provider policy, defaulting available when secure prerequisites are configured, encrypted attempt storage and worker-independent callbacks; authorization never enables execution. See the [foundation specification](../../../../docs/operations/personal-downstream-mcp-oauth-specification.md), [catalogue iteration](../../../../docs/operations/personal-downstream-mcp-catalogue-specification.md) and [authorization iteration](../../../../docs/operations/personal-downstream-mcp-authorization-specification.md).

### Other

### `messaging/`

**Read when working with:** Core messaging contracts shared with transport implementations. `stores/event_stream.py` provides durable stream storage and `append_event_in_session` for atomic state-and-event writes.

### `telemetry/`

**Read when working with:** Validated telemetry exports, sink ports, in-memory acceptance, or existing stdout logger integration.

### `persistence/`

**Read when working with:** Persistence ports, queries, or database readiness behavior.

**Dependency rule:** Shared root packages never import `umbod_sdk.connectors.native`, `umbod_sdk.connectors.openapi`, or `umbod_sdk.connectors.downstream_mcp`. Kind packages and delivery boundaries may import shared roots. Kind-stitching composition belongs in delivery wiring (for example REST).
