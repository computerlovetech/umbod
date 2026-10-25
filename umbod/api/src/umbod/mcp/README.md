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

Connector kinds are grouped under `native/`, `openapi/`, and `downstream_mcp/`, matching the REST connector module structure. The package's public API exports only the lazily loaded `native`, `openapi`, and `downstream_mcp` namespaces. Each kind owns its public objects through its package exports; implementation helpers are not promoted to the root API. These are backend composition APIs, not a replacement for the supported `umbod.hosting` integration boundary. Tests should exercise registration and invocation behavior rather than call private helpers.

### `connectors/native/`

**Read when working with:** Native connector tool registration, exposure modes, approval, invocation, or direct request-lifetime file input apps.

File-input connector tools keep uploaded bytes only for the current app-backend invocation. Policy and approval receive only filename, media type, size, and SHA-256 metadata. Approval-required invocations cannot be resumed because no upload storage exists; callers must submit the file again after approval. File-input connector tools currently support only flat exposure; gateway and codemode registration reject them.

### `connectors/downstream_mcp/`

**Read when working with:** Downstream discovery, reconciliation, publication, or invocation.

`connectors/downstream_mcp/tool_projection.py` is the pure descriptor projection shared by shared and personal tool materialization, preserving SDK metadata, tags, annotations, icons, execution and output-schema presence without deriving trusted invocation identity from metadata. Successful personal results preserve validated result `_meta`, content and structured output; failures remain sanitized without downstream metadata.

`connectors/downstream_mcp/principal.py` exposes `McpCanonicalPrincipalProvider(settings)`. It captures narrow personal policy at construction and reads current SDK authentication on every call. Shared feature adapters translate accepted claims into immutable identity facts; core's `PersonalIdentityPrincipalProvider` resolves them without AppConfig, raw JWT dictionaries or framework state. It does not decode or trust the outer proxy issuer, cache principals or enable runtime execution.

Personal principal/runtime adapters normalize an already authenticated local `single_test_user` context through `core/connectors/downstream_mcp/adapters/identity.py` to the same configured REST Test User. Eligibility remains a typed core policy in `personal_connections/development_identity.py`. Missing context and original machine claims remain denied. This projection does not mutate global MCP/shared/native token claims or invent membership under a different MCP group claim.

Personal OAuth definitions remain unavailable to shared runtime execution and background discovery. `connectors/downstream_mcp/personal_runtime.py` reads the current verified access-token claims on every context lookup using the REST-equivalent canonical principal and group policy. `public_app.py` selects the active tools-only runtime only when both personal selection and OAuth policies are enabled; all other profiles use the disabled adapter. `provider.py` merges the current owner’s private discovered inventory into the existing provider without consulting the legacy global personal tool policy, per-tool activation or per-tool grants and fails closed on shared/personal public-name collisions. `tool_invocation.py` shares approval, validation and telemetry between real shared proxy delegation and personal runtime delegation; invocation-local bounded core diagnostics enrich the single existing ERROR completion with `mcp.failure.stage`, `mcp.failure.reason` and `mcp.execution_mode`, without changing client responses, audit categories or metric labels; held personal tools retain only public contract metadata and identity/revision/fingerprint, never an owner or credential. Personal admission runs again after approval, including gateway/codemode internal calls. Global auth dispatches the server-owned `AuthorizedPersonalTool` component type through authoritative personal availability instead of cached group allow/deny; metadata cannot select this path. Component cloning preserves that type. `PersonalToolReservationMiddleware` remains installed even when personal execution is disabled. It reserves personal definition namespaces independently of global catalogs, owner availability, stored observations and publication, rejects alternate resolved component types and filters conflicting listing metadata. Namespace stems use public-name mangling; ambiguous empty stems fail closed. Personal connector scope reserves unprefixed names. Gateway and codemode collision checks apply the same namespace predicate before native dispatch. Gateway dispatch validates configured native/provider name claims before eligibility or execution, so an unavailable personal tool cannot fall through to another provider. Unpublished shared drafts do not reserve names. `provider.py` composes core's `downstream_mcp/runtime/` resolver with shared stores and full capability availability. Every operation factory binds the complete capability identity and resolves afresh, including held tools after invocation approval. `resource_access.py` uses access-checked template and resource wrappers to recheck full capability availability before template creation and cached-content reads. There is no connector-only fallback factory. Shared group permissions still use polling memory, so cross-worker grant revocation is not immediate. Admission does not bind a catalogue contract fingerprint; a held tool can retain its previously listed schema. Personal tools instead bind the listed private inventory revision and fingerprint, validate output offline and use a fresh operation-scoped live-contract preflight. Rediscovery is required before new tools appear; retained tools cannot cross an inventory revision. Current server grants, group membership, owner enablement and OAuth authorization are checked again after approval. Resources, prompts, templates and retained shared-content wrappers remain shared-only.

### `connectors/openapi/`

**Read when working with:** MCP exposure and execution of OpenAPI-generated operations.

### `auth/`

**Read when working with:** MCP OAuth, client storage, authorization, or consent. `caller.py` maps the current SDK token to `core/callers` observations through a stateless provider and an injectable FastMCP dependency. Provenance comes from the actual server authentication provider, not token claims. Missing authentication is explicit; known local test providers never claim upstream verification. Host-supplied or inherited SDK authentication is classified conservatively. Existing group and canonical-owner projections remain separate. `groups.py` captures typed unqualified memberships with distinct runtime, OpenAPI and administrator policies; their legacy coercion, filtering and ordering differences are preserved. The identical personal parser is shared with REST through the downstream feature adapter.

`auth/factory.py` leaves the Google, Entra, and Auth0 OAuth proxy issuer at FastMCP's public MCP base URL default. MCP resource metadata advertises Umbod's authorization server, and authorization metadata exposes Umbod's authorize, token, and register endpoints. Shared `oidc.issuer_url` remains the upstream token issuer for REST validation; Auth0 discovery independently supplies the upstream MCP token verifier's issuer.

### `authorization.py`

**Read when working with:** FastMCP component identity adaptation and group-grant permission callbacks. The bridge owns tool/prompt/resource/template metadata and SDK authentication-context handling; `core/permissions` retains neutral grant decisions over typed `GroupMembership`, without importing FastMCP or parsing claims. Native, downstream and global permission consumers capture memberships before invoking core. Checker imports now use `umbod.mcp.authorization`, not core permission exports.

### `messaging/`

**Read when working with:** Event transport and state synchronization used by the MCP process.

### `logging/`, `metrics/`, `middleware/`, and `tools/`

**Read when working with:** Audit behavior, instrumentation, protocol request handling, or observed registration of internal FastMCP tools. `tools/registration.py` preserves callable-derived FastMCP metadata while observing the complete `FunctionTool.run` lifecycle; `tools/invocation/` contains shared invocation lifecycle and telemetry behavior.

## Embedded host composition

Supported hosts use [`umbod.hosting`](../hosting/README.md) and `create_mcp_app`; `PublicAppConfig` and runtime contexts remain backend internals. `main.py` delegates to `umbod.hosting.mcp_service:app`, the separate service bootstrap.

The `invocation_log_sink` hook on `create_mcp_app` supplies a deployment-owned completed-invocation sink; the normal structured logger remains the default. `live_permission_updates.py` reads group permissions from the shared database when SQL messaging is selected, or the system HTTP API for HTTP messaging. This allows embedded REST/MCP applications to synchronize permissions without exposing an unauthenticated internal API.
