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

`approval_principal.py` exposes a fresh approval caller capture boundary over invocation actor identity. `approval.py` captures its immutable binding once per Ask evaluation, including continuations; `approval_state.py` preserves the existing client/user or session-only wire binding without substituting canonical ownership or authentication observations.

`tools/invocation/runner.py` captures connector failure evidence only around the actual native operation call and await; result adaptation failures remain internal. `tools/invocation/identity.py` owns the required connector invocation identity without lifecycle aliases or unused normalization helpers. `tools/registration.py` requires neutral MCP signals and an execution-pipeline factory, publishes the validated native inventory once, and passes a signal publisher to fixed-tool registration. `tools/runtime/registry.py` builds native runners through the injected pipeline factory without logging, audit, or metrics dependencies. Shared signal execution publishes completions; central listeners own observation adapters.

File-input connector tools keep uploaded bytes only for the current app-backend invocation. Policy and approval receive only filename, media type, size, and SHA-256 metadata. Approval-required invocations cannot be resumed because no upload storage exists; callers must submit the file again after approval. File-input connector tools currently support only flat exposure; gateway and codemode registration reject them.

### `connectors/downstream_mcp/`

**Read when working with:** Downstream discovery, reconciliation, publication, or invocation.

`connectors/downstream_mcp/permissions.py` separates current-caller capture from grant evaluation. Capture sources produce an immutable `CallerContext` and membership snapshot; listing loops reuse it while consulting current grant state. `provider.py` builds availability and shared runtime resolution per operation, never retaining caller-bound evaluators on shared providers or materialized tools.

`connectors/downstream_mcp/inventory.py` projects persisted shared tool identities into neutral `ToolInventoryObserved` events for startup and catalog refresh, including prefixed and connector-scoped routes without enumerating personal inventories. Shared materialization publishes only its actual public identity; personal listing publishes no inventory. Providers receive signals and an execution-pipeline factory, and materialized tools receive ready pipelines instead of telemetry dependencies.

`connectors/downstream_mcp/tool_projection.py` is the pure descriptor projection shared by shared and personal tool materialization, preserving SDK metadata, tags, annotations, icons, execution and output-schema presence without deriving trusted invocation identity from metadata. Successful personal results preserve validated result `_meta`, content and structured output; failures remain sanitized without downstream metadata.

`connectors/downstream_mcp/personal_runtime.py` exposes `McpPersonalCallerProvider(settings)`. Each lookup captures one current token into a shared caller observation and resolves immutable canonical ownership and strict membership from that same token. Provenance follows the active server authentication provider, not deployment settings; absent context is unavailable. `McpPersonalToolRuntime` implements the runtime port at the delivery boundary, capturing through the deferred caller port for each listing or execution and constructing an operation-local core service. This preserves retained invocation and post-approval freshness without caching callers. Core services accept only captured `PersonalCaller` or explicit unavailable values, never capture callbacks.

Personal caller adapters normalize an already authenticated local `single_test_user` context through `core/connectors/downstream_mcp/adapters/identity.py` to the same configured REST Test User. Eligibility remains a typed core policy in `personal_connections/development_identity.py`. Missing context and original machine claims remain denied. This projection does not mutate global MCP/shared/native token claims or invent membership under a different MCP group claim.

Personal OAuth definitions remain unavailable to shared runtime execution and background discovery. `connectors/downstream_mcp/personal_runtime.py` captures the current accepted access-token claims on every caller lookup using the REST-equivalent canonical principal and group policy. `public_app.py` selects the active tools-only runtime only when both personal selection and OAuth policies are enabled; all other profiles use the disabled adapter. `provider.py` merges the current owner’s private discovered inventory into the existing provider without consulting the legacy global personal tool policy, per-tool activation or per-tool grants and fails closed on shared/personal public-name collisions. `tool_invocation.py` shares approval, validation and telemetry between real shared proxy delegation and personal runtime delegation; invocation-local bounded core diagnostics enrich the single existing ERROR completion with `mcp.failure.stage`, `mcp.failure.reason` and `mcp.execution_mode`, without changing client responses, audit categories or metric labels; held personal tools retain only public contract metadata and identity/revision/fingerprint, never an owner or credential. Personal admission runs again after approval, including gateway/codemode internal calls. Global auth dispatches the server-owned `AuthorizedPersonalTool` component type through authoritative personal availability instead of cached group allow/deny; metadata cannot select this path. Component cloning preserves that type. `PersonalToolReservationMiddleware` remains installed even when personal execution is disabled. It reserves personal definition namespaces independently of global catalogs, owner availability, stored observations and publication, rejects alternate resolved component types and filters conflicting listing metadata. Namespace stems use public-name mangling; ambiguous empty stems fail closed. Personal connector scope reserves unprefixed names. Gateway and codemode collision checks apply the same namespace predicate before native dispatch. Gateway dispatch validates configured native/provider name claims before eligibility or execution, so an unavailable personal tool cannot fall through to another provider. Unpublished shared drafts do not reserve names. `provider.py` composes core's `downstream_mcp/runtime/` resolver with shared stores and full capability availability. Every operation factory binds the complete capability identity and resolves afresh, including held tools after invocation approval. `resource_access.py` uses access-checked template and resource wrappers to recheck full capability availability before template creation and cached-content reads. There is no connector-only fallback factory. Shared group permissions still use polling memory, so cross-worker grant revocation is not immediate. Admission does not bind a catalogue contract fingerprint; a held tool can retain its previously listed schema. Personal tools instead bind the listed private inventory revision and fingerprint, validate output offline and use a fresh operation-scoped live-contract preflight. Rediscovery is required before new tools appear; retained tools cannot cross an inventory revision. Current server grants, group membership, owner enablement and OAuth authorization are checked again after approval. Resources, prompts, templates and retained shared-content wrappers remain shared-only.

### `connectors/openapi/`

`connectors/openapi/inventory.py` projects persisted OpenAPI connector identities into neutral inventory events before traffic. `codemode_execution.py` receives an execution-pipeline factory; centrally registered listeners own invocation logging, metrics and audit.

**Read when working with:** MCP exposure and execution of OpenAPI-generated operations. `deps.py` captures immutable OpenAPI membership at operation entry; discovery and codemode pass its tuple into existing core APIs. There is no generic principal/subject callback or native-to-OpenAPI caller-provider dependency. `codemode_execution.py` preserves successful HTTP transport results in the public response while recording HTTP statuses >=400 as failed tool invocations with OpenAPI-origin evidence; HTTP 2xx/3xx remain telemetry successes. Returned failures include no response body or invented exception traceback.

### `auth/`

**Read when working with:** MCP OAuth, client storage, authorization, or consent. `caller.py` maps the current SDK token to `core/callers` observations through direct immutable capture and an injectable FastMCP dependency. `caller_context_from_access_token` projects an already-read token without another SDK lookup; generic caller-provider wrappers are removed. Provenance comes from the actual server authentication provider, not token claims. Missing authentication is explicit; known local test providers never claim upstream verification. Host-supplied or inherited SDK authentication is classified conservatively. Existing group and canonical-owner projections remain separate. `groups.py` captures typed unqualified memberships with distinct runtime, OpenAPI and administrator policies; their legacy coercion, filtering and ordering differences are preserved. The identical personal parser is shared with REST through the downstream feature adapter.

`auth/factory.py` leaves the Google, Entra, and Auth0 OAuth proxy issuer at FastMCP's public MCP base URL default. MCP resource metadata advertises Umbod's authorization server, and authorization metadata exposes Umbod's authorize, token, and register endpoints. Shared `oidc.issuer_url` remains the upstream token issuer for REST validation; Auth0 discovery independently supplies the upstream MCP token verifier's issuer.

### `authorization.py`

**Read when working with:** FastMCP component identity adaptation and group-grant permission callbacks. The bridge owns tool/prompt/resource/template metadata and SDK authentication-context handling; `core/permissions` retains neutral grant decisions over typed `GroupMembership`, without importing FastMCP or parsing claims. Native, downstream and global permission consumers capture memberships before invoking core. Checker imports now use `umbod.mcp.authorization`, not core permission exports.

### `filesystem/`

**Read when working with:** Filesystem browsing and empty node creation over MCP. See [the local module index](filesystem/README.md) for tool, error, snapshot, lifetime, and bootstrap contracts. `registration.py` publishes exactly `get_filesystem_root`, `get_filesystem_node`, `list_filesystem_children`, `create_filesystem_file`, and `create_filesystem_directory` through the observed registrar. Node IDs and parent IDs are UUIDs. Creation requires `parent_id`, `name`, and `metadata: NodeMetadata`; caller identity, ownership, grants, and content are not accepted inputs. Root, node, and creation results are safe `NodeSummary` objects; children return the named `{nodes: [NodeSummary, ...]}` envelope. Summaries never expose content storage keys, owners, or grants.

`caller.py` captures one current token per invocation and derives provenance from the actual server authentication provider. Membership uses active runtime permission claim fields, falling back to the configured MCP group claim only when no permission runtime state exists. Core's verified identity resolver alone decides authority; local test, unavailable, and deployment-only observations cannot authorize filesystem access. No caller, session, or application service is retained across invocations. `factory.py` constructs operation-local core browsing and creation services over the prepared application database, without a content driver.

Authorization, list filtering, name validation, ownership, and persistence remain core responsibilities. Missing and denied nodes share `filesystem_permission_denied`; other expected failures use fixed `filesystem_invalid_name`, `filesystem_name_collision`, `filesystem_wrong_node_kind`, and `filesystem_storage_failure` messages without raw exception details. Unexpected failures produce the fixed `filesystem_operation_failed: Filesystem operation failed` error. Read tools are read-only and idempotent; creation is non-idempotent and creates empty private nodes. The tools do not provision a root or grant access: an operator must bootstrap the system-owned root and initial discover/write grants through the separate provisioning boundary before clients can use them.

### `messaging/`

**Read when working with:** Event transport and state synchronization used by the MCP process.

### `signals/` and `listeners/`

`signals/` owns neutral immutable invocation and inventory facts, application-scoped named signal channels, shared context, lifecycle publication, and the execution-pipeline factory. Concrete native, downstream MCP, and OpenAPI implementations depend on these neutral contracts, not telemetry adapters. A new side effect subscribes to the existing typed signal without editing tool implementations. Receiver execution is synchronous and ordinary failures are isolated; cancellation and process-control exceptions are not swallowed.

`listeners/registration.py` is the single explicit registration point for invocation logging, metrics, audit, and inventory metric receivers. `public_app.py` creates one signal set per application before registering tools or publishing inventory. There are no global receivers or import-time subscriptions. Audit receivers exclude middleware-owned orchestration completions so code hashes, authorization denials, and existing audit ownership remain intact. Invocation event, context, lifecycle and diagnostic imports use their canonical `signals/` modules; logging exports only concrete logging and audit contracts. See the [signals index](signals/README.md) and [listeners index](listeners/README.md).

### `logging/`, `metrics/`, `middleware/`, and `tools/`

**Read when working with:** Audit behavior, instrumentation, protocol request handling, or observed registration of internal FastMCP tools. Failed completion logs carry `mcp.failure.origin` independently of audit categories and metric labels; exception failures include safe `exception.type` and `exception.stacktrace` snapshots, while returned failures have no invented traceback. Raw exception messages, source lines, locals and credential values are excluded. Audit/invocation actor projection consumes the shared captured subject while retaining the separate email/preferred-username fallback and client/session metadata rules. `tools/registration.py` preserves callable-derived FastMCP metadata while observing the complete `FunctionTool.run` lifecycle and attaching internal failure evidence without exception messages, source text, or locals; `signals/lifecycle.py` owns the shared invocation lifecycle; publication and side effects live in `signals/` and `listeners/`. Native deployment factories receive an explicit observed registrar for `search_tools`, `execute_tool`, and `execute_code`, preserving tags, metadata, schemas, and public results. Fixed-tool completions have request scope, independently of nested connector-scoped completions. Codemode classifies structured failure and timeout outcomes without changing `is_error`. Fixed tools publish neutral completions; audit middleware owns their single audit event, including ordinary exceptions, gateway returned errors, and codemode code hashes. Authorization denials retain their existing audit path; cancellation is not completed or audited.

### Metric counting contract

`umbod_mcp_tool_invocations_total` and its duration histogram count connector executions only. `umbod_mcp_tool_requests_total` and its duration histogram count observed built-in and orchestration tool lifecycles, independently of their nested executions. Completion logs carry `mcp.invocation.scope` (`connector` or `request`) so investigations can compare the same scope rather than all ERROR records. One gateway request can produce one connector execution; one codemode request can produce zero or many executions. A script that handles a connector failure can itself succeed.

Native mapping registration, fixed-tool registration, persisted OpenAPI inventory and shared downstream inventory initialize both success and failure series with zero counts. Downstream refresh and shared tool materialization publish inventory facts; the inventory receiver initializes newly known identities idempotently. Initialization does not produce completion logs, audit events or duration observations. Private inventories are not queried just to seed metrics. Dynamically introduced identities and traffic before the first scrape can still lack a preceding sampled zero; Prometheus `increase` remains a scrape-based estimate.

Raised failures and returned error results count as failures. OpenAPI HTTP status 400 or higher counts as a failed connector execution while preserving its transport response. Cancellation and approval-required interruptions retain their existing no-completion behavior; authorization denials remain separately audited. Instrumentation failures are logged and do not replace invocation results.

## Embedded host composition

Supported hosts use [`umbod.hosting`](../hosting/README.md) and `create_mcp_app`; `PublicAppConfig` and runtime contexts remain backend internals. `main.py` delegates to `umbod.hosting.mcp_service:app`, the separate service bootstrap.

The `invocation_log_sink` hook on `create_mcp_app` supplies a deployment-owned completed-invocation sink; the normal structured logger remains the default. `live_permission_updates.py` reads group permissions from the shared database when SQL messaging is selected, or the system HTTP API for HTTP messaging. This allows embedded REST/MCP applications to synchronize permissions without exposing an unauthenticated internal API.
