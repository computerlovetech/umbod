# ADR-008: Event-Synchronized In-Memory Tool Runtime

- **Status:** Accepted
- **Date:** Not recorded
- **Scope:** MCP tool discovery, runtime synchronization, and invocation authority

## Decision

Shared MCP tool discovery reads an application-scoped, in-memory runtime catalog maintained by startup loading and event-driven reconciliation. Persistent stores remain the durable source of truth; the runtime catalog is a derived read model, not a second source of configuration.

This contract applies consistently to native, OpenAPI, and shared downstream MCP tools. Flat and connector-scoped discovery, gateway search, code-mode discovery, name ownership and collision checks consume the same logical catalog. Connector-specific adapters may differ, but connector kind and exposure mode must not select a separate database-backed discovery pipeline.

Personal connector inventories are an explicit exception to the fully in-memory discovery contract. Owner-specific tool descriptors and connection availability may be read from persistence through a bounded, coherent, read-only snapshot per discovery operation. Personal discovery must not reserve the database writer slot or reload the owner's complete inventory for each returned tool. Shared connector metadata, namespace reservations and group-grant projections remain event-synchronized in memory; the exception must not introduce persistent shared-catalog discovery.

Personal discovery-affecting mutations still publish durable change events atomically with their state changes. Events notify changes without carrying credentials, owner identifiers or private tool schemas. The exception does not require every MCP worker to preload or retain every owner's inventory. Any retained private metadata requires explicit owner isolation, bounded retention and event-driven invalidation. Discovery remains separate from authoritative execution admission and operation-scoped credential retrieval.

The architecture requires one logical shared catalog per MCP application, not one process-global singleton or one mandatory implementation class. Each worker owns its own instance. Runtime state and synchronization dependencies are composed explicitly and injected through ports. Hosts use the same backend implementation, following ADR-004.

The [supporting detail](supporting/tool-runtime.md) preserves the accepted constraints and verification requirements that accompany this decision.

## Context and rationale

Before this migration, Umbod registered native tools in an application-scoped runtime and reconciled changes through messaging, while shared downstream MCP discovery reloaded persisted definitions and catalogs and reconstructed capabilities during requests. Namespace reservation also loaded downstream definitions while listing otherwise registered tools. Tool discovery therefore had different lifetime and I/O behavior depending on connector kind.

A regression through the public MCP client demonstrated that a single shared connector with 40 tools caused 122 full-definition reads in one tools/list request. Catalog readiness also reconstructed a connector's capabilities for each tool. Request-local deduplication reduces this amplification but does not establish the intended runtime architecture.

Personal inventories vary by owner and can scale with the number of users, connections and tool descriptors. Replicating every private inventory into every MCP worker would make memory consumption grow with both user population and worker count. The personal-inventory exception permits bounded persistence reads without weakening shared discovery, messaging or ownership boundaries.

ADR-001 establishes the shared persistence runtime and neutral database boundary. It does not establish the tool discovery read model. This decision adds that boundary without changing persistence ownership, credential storage policy, or MCP authentication.

## Alternatives considered

The original alternatives evaluation was not recorded. The personal-inventory amendment rejects mandatory preloading of all private inventories into every worker because of memory growth and owner-lifecycle synchronization costs. A bounded, event-invalidated owner cache remains optional, not a prerequisite or a substitute for authoritative execution checks.

## Consequences

Shared discovery cost depends on runtime filtering and result size rather than database round trips or downstream availability. Shared connector kinds follow one lifetime and synchronization contract, and namespace protection no longer introduces catalog queries into native tool listing.

Personal discovery may depend on persistence availability and bounded read latency, but does not require all private inventories to reside in memory. It must preserve coherent owner-specific reads without writer reservations or per-tool inventory reconstruction. This exception does not justify the existing read/write transaction ambiguity or claim that current personal discovery already meets these constraints.

The application retains more metadata in memory and must own reliable startup, revision handling, reconciliation and recovery. Consistency is explicitly bounded by event delivery rather than implied by a cache. Security-sensitive execution remains fresh and separate from the discovery read model.

## Confidence and reevaluation

Confidence and decision date were not recorded. The context reports 122 definition reads for 40 tools but does not link the originating regression evidence. The consistency window remains an implementation obligation, not a measured guarantee. Reevaluate through a new ADR if event lag, memory use, or caller isolation cannot meet the recorded discovery and execution contracts.

## Supporting material

- [Accepted constraints and supporting detail](supporting/tool-runtime.md)

- [ADR-001: Backend-Neutral Persistence Module Boundaries](ADR-001-backend-neutral-persistence.md)
- [ADR-004: One Backend API and a Thin Desktop Boundary](ADR-004-single-backend-api-and-desktop-boundary.md)
- [ADR-002: Client-Owned Credentials for Multi-Provider MCP Tool Authentication](ADR-002-client-side-credential-storage.md), Proposed; credential ownership is outside this decision.
