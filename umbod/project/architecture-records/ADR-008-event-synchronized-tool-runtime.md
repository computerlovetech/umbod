# ADR-008: Event-Synchronized In-Memory Tool Runtime

## Status

Accepted. Native, OpenAPI and shared downstream discovery use application-scoped projections synchronized through durable messaging. Execution authorization remains operation-scoped.

## Context

Before this migration, Umbod registered native tools in an application-scoped runtime and reconciled changes through messaging, while shared downstream MCP discovery reloaded persisted definitions and catalogs and reconstructed capabilities during requests. Namespace reservation also loaded downstream definitions while listing otherwise registered tools. Tool discovery therefore had different lifetime and I/O behavior depending on connector kind.

A regression through the public MCP client demonstrated that a single shared connector with 40 tools caused 122 full-definition reads in one tools/list request. Catalog readiness also reconstructed a connector's capabilities for each tool. Request-local deduplication reduces this amplification but does not establish the intended runtime architecture.

ADR-001 establishes the shared persistence runtime and neutral database boundary. It does not establish the tool discovery read model. This decision adds that boundary without changing persistence ownership, credential storage policy, or MCP authentication.

## Decision

MCP tool discovery reads an application-scoped, in-memory runtime catalog maintained by startup loading and event-driven reconciliation. Persistent stores remain the durable source of truth; the runtime catalog is a derived read model, not a second source of configuration.

This contract applies consistently to native, OpenAPI, and shared downstream MCP tools. Flat and connector-scoped discovery, gateway search, code-mode discovery, name ownership and collision checks consume the same logical catalog. Connector-specific adapters may differ, but connector kind and exposure mode must not select a separate database-backed discovery pipeline.

The architecture requires one logical catalog per MCP application, not one process-global singleton or one mandatory implementation class. Each worker owns its own instance. Runtime state and synchronization dependencies are composed explicitly and injected through ports. Hosts use the same backend implementation, following ADR-004.

### Runtime contents and discovery boundary

The runtime holds validated tool descriptors, complete capability identities, connector routing metadata, normalized namespace reservations, catalog revisions, publication and activation projections, readiness facts, and capability-description overrides needed for discovery. Build indexes and normalize schemas during loading or reconciliation, not once per returned tool.

Shared discovery must not query persistent connector definitions or catalogs, decrypt credentials, contact downstream services, or reconstruct complete connector catalogs. This includes middleware, fallback component lookup, connector-scoped routing, gateway name validation and nested provider resolution. A lazy or request-local cache over those reads does not satisfy this contract.

Readiness projections contain availability facts, not decrypted credentials or live clients. Runtime tools do not retain caller identity, bearer credentials, approval decisions or a caller-bound authorization evaluator.

Each discovery operation captures a stable runtime snapshot and the current caller's membership at its public boundary. Caller filtering remains request-local. Group-grant evaluation must retain the existing current-grant semantics rather than freezing final allow/deny decisions in tool descriptors. Snapshot capture must not move caller capture after asynchronous loading.

### Startup and synchronization

1. Prepare the application's shared persistence runtime and establish the event-stream position needed for a race-free bootstrap.
2. Load and validate the initial runtime projection before declaring MCP discovery ready. Startup must account for changes committed during that load; simply loading and then subscribing can lose events.
3. Consume durable change events through the existing messaging ports, with independently advancing delivery state for every live runtime instance. Workers must not share a consumer cursor that causes one worker to consume another worker's updates.
4. Reconcile all changes that affect discovery: definition creation, edits and deletion; namespace and public-path changes; configuration and credential availability; catalog replacement and rediscovery; publication; activation; group grants; and description overrides.
5. Persist state changes and their durable change events atomically where they share the database. Downstream refresh feeds that same reconciliation path rather than updating an unrelated private cache.
6. Apply changes idempotently, respecting event order and revision semantics. Ignore obsolete updates and remove old names, routes and reservations when identities change. Deletion and unpublication must not leave executable aliases or permit fallback to a conflicting provider.
7. Construct replacement projections completely before publishing them atomically. A request observes a coherent snapshot, not partially updated dictionaries. Do not hold runtime locks while performing persistence or network I/O.
8. Advance checkpoints only after successful application. Retry failures without silently skipping changes. Expose synchronization failures and lag. Until a complete initial projection exists, or when a detected synchronization failure makes availability unsafe, fail closed for affected capabilities rather than serving an unbounded stale authorization view.
9. Shut down synchronization with the owning application. Replay or startup rebuilding restores the projection after restart.

Polling a durable event stream is a valid messaging transport. Periodic full-state reloads may be an explicit recovery mechanism, but TTL caching, timer-only refresh and per-request rebuilding are not substitutes for change-event coverage. The implementation must document its consistency window; this ADR does not claim instantaneous cross-worker revocation.

### Authorization and personal tools

Discovery is not execution authority. Invocation, retained tools and approval continuations must resolve current caller authority and capability availability again at the existing execution boundary. An older discovery snapshot must not bypass revocation, owner disablement, credential changes, catalog revision checks or post-approval admission. Credential retrieval and downstream connections remain operation-scoped.

Personal tool inventories are owner-specific, not entries in the shared public catalog. Their descriptors must remain isolated by canonical owner, connector and inventory revision, including concurrent requests. If private metadata is retained in memory, it uses explicit owner partitions and invalidation; it must never leak through shared lookup, metrics initialization or a previous caller's cached listing.

The shared namespace index reserves personal connector namespaces independently of owner availability, private inventory, publication and personal-execution feature flags. Preserve mangled-prefix matching, connector-scoped unprefixed reservations, ambiguous-prefix rejection and authoritative resolved-component type checks. Metadata cannot turn a shared component into an authorized personal tool.

Bounded personal admission and authoritative execution checks may perform operation-scoped I/O where their security contracts require it. These are explicit authority boundaries, not permission to reload the shared catalog or scan all definitions per tool. This decision does not replace personal credential, ownership, revision or fingerprint policies, or promote the proposed ADR-002 credential model to Accepted.

## Enforcement and acceptance

Changes to tool registration, discovery, namespace ownership, provider lookup, reconciliation, messaging or invocation admission must be reviewed against this ADR before implementation. Any exception must be explicit in an ADR, not hidden in a connector adapter.

Verification must cover public interfaces and include:

- Shared tools/list and search succeed from the initialized runtime with persistent definition/catalog reads and downstream discovery disabled at the test boundary.
- Increasing tools on one connector does not increase definition scans, credential reads or full-catalog reconstruction. Query-count assertions complement latency measurements; elapsed-time thresholds alone are insufficient.
- Every discovery-affecting mutation updates all running runtime instances through messaging without reconnecting clients or relying on a new discovery request to trigger refresh.
- Startup changes, replay, duplicate and obsolete events, failed reconciliation, checkpoint handling, deletion, restart and cancellation preserve the synchronization contract.
- Root and scoped endpoints, flat, gateway and code-mode exposure preserve consistent identities and collision handling.
- Concurrent callers and personal inventories remain isolated. Retained tools and approval continuations recheck authority after revocation and inventory changes.
- Protocol discovery timings and synchronization health are observable without tokens, private schemas, owner identifiers or unbounded tool-name metric labels.

Applicable backend, lint, shared Semgrep and Kind runtime checks remain required by AGENTS.md. Acceptance of this decision is not evidence that any verification command has passed; verification results must be reported separately.

## Implementation ownership

`mcp/connectors/downstream_mcp/runtime/` owns the shared downstream snapshot port, loader and in-memory adapter, including namespace reservations. The provider and scoped dispatcher consume initialized snapshots. `mcp/connectors/openapi/discovery_runtime.py` owns the OpenAPI structural projection, with current grants evaluated outside it. Native registration and search are refreshed through the native runtime registry.

`mcp/messaging/projection.py` owns the single projection consumer. Bootstrap establishes a pre-load event fence, hydrates once, then replays changes committed during loading. Every live application owns independent delivery state. The application lifespan composes reconciliation and failure gating. Event constructors use generic messaging ports; retired connector-specific pollers, typed stream wrappers and route-level publishers are removed rather than retained as parallel paths.

Durable mutation owners append events in their state transaction. Downstream probe admission additionally captures definition, credential, catalog state and durable generation before external I/O; successful and failed results compare that admission inside the applying transaction. Deleted identities retain generation tombstones so an older probe cannot recreate their state.

Query-budget regressions prohibit steady-state shared definition, catalog, credential and publication reads during discovery. Native and downstream invocations recheck authority after approval, and OpenAPI execution remains authoritative. Module README indexes describe the current entrypoints and ownership.

## Consequences

Discovery cost depends on runtime filtering and result size rather than database round trips or downstream availability. Connector kinds follow one lifetime and synchronization contract, and namespace protection no longer introduces catalog queries into native tool listing.

The application retains more metadata in memory and must own reliable startup, revision handling, reconciliation and recovery. Consistency is explicitly bounded by event delivery rather than implied by a cache. Security-sensitive execution remains fresh and separate from the discovery read model.

## Related decisions

- [ADR-001: Backend-Neutral Persistence Module Boundaries](ADR-001-backend-neutral-persistence.md)
- [ADR-004: One Backend API and a Thin Desktop Boundary](ADR-004-single-backend-api-and-desktop-boundary.md)
- [ADR-002: Client-Owned Credentials for Multi-Provider MCP Tool Authentication](ADR-002-client-side-credential-storage.md), Proposed; credential ownership is outside this decision.
