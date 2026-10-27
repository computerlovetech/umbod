# ADR-008: Event-Synchronized In-Memory Tool Runtime

- **Status:** Accepted
- **Date:** Not recorded
- **Scope:** MCP tool discovery, runtime synchronization, and invocation authority

## Decision

MCP tool discovery reads an application-scoped, in-memory runtime catalog maintained by startup loading and event-driven reconciliation. Persistent stores remain the durable source of truth; the runtime catalog is a derived read model, not a second source of configuration.

This contract applies consistently to native, OpenAPI, and shared downstream MCP tools. Flat and connector-scoped discovery, gateway search, code-mode discovery, name ownership and collision checks consume the same logical catalog. Connector-specific adapters may differ, but connector kind and exposure mode must not select a separate database-backed discovery pipeline.

The architecture requires one logical catalog per MCP application, not one process-global singleton or one mandatory implementation class. Each worker owns its own instance. Runtime state and synchronization dependencies are composed explicitly and injected through ports. Hosts use the same backend implementation, following ADR-004.

The [supporting detail](supporting/tool-runtime.md) preserves the accepted constraints and verification requirements that accompany this decision.

## Context and rationale

Before this migration, Umbod registered native tools in an application-scoped runtime and reconciled changes through messaging, while shared downstream MCP discovery reloaded persisted definitions and catalogs and reconstructed capabilities during requests. Namespace reservation also loaded downstream definitions while listing otherwise registered tools. Tool discovery therefore had different lifetime and I/O behavior depending on connector kind.

A regression through the public MCP client demonstrated that a single shared connector with 40 tools caused 122 full-definition reads in one tools/list request. Catalog readiness also reconstructed a connector's capabilities for each tool. Request-local deduplication reduces this amplification but does not establish the intended runtime architecture.

ADR-001 establishes the shared persistence runtime and neutral database boundary. It does not establish the tool discovery read model. This decision adds that boundary without changing persistence ownership, credential storage policy, or MCP authentication.

## Alternatives considered

An alternatives evaluation was not recorded. The context describes the competing pressures, but does not establish which alternatives were seriously considered or their full trade-offs.

## Consequences

Discovery cost depends on runtime filtering and result size rather than database round trips or downstream availability. Connector kinds follow one lifetime and synchronization contract, and namespace protection no longer introduces catalog queries into native tool listing.

The application retains more metadata in memory and must own reliable startup, revision handling, reconciliation and recovery. Consistency is explicitly bounded by event delivery rather than implied by a cache. Security-sensitive execution remains fresh and separate from the discovery read model.

## Confidence and reevaluation

Confidence and decision date were not recorded. The context reports 122 definition reads for 40 tools but does not link the originating regression evidence. The consistency window remains an implementation obligation, not a measured guarantee. Reevaluate through a new ADR if event lag, memory use, or caller isolation cannot meet the recorded discovery and execution contracts.

## Supporting material

- [Accepted constraints and supporting detail](supporting/tool-runtime.md)

- [ADR-001: Backend-Neutral Persistence Module Boundaries](ADR-001-backend-neutral-persistence.md)
- [ADR-004: One Backend API and a Thin Desktop Boundary](ADR-004-single-backend-api-and-desktop-boundary.md)
- [ADR-002: Client-Owned Credentials for Multi-Provider MCP Tool Authentication](ADR-002-client-side-credential-storage.md), Proposed; credential ownership is outside this decision.
