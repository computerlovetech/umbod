# ADR-001: Backend-Neutral Persistence Module Boundaries

- **Status:** Accepted
- **Date:** Not recorded
- **Scope:** Persistence boundaries and REST/MCP application lifetimes

## Decision

Each REST or MCP application creates exactly one application-scoped `PersistenceRuntime` at its composition root. The runtime exposes a backend-neutral `Database` and concurrency-safe `PersistenceReadiness`. All persistent bounded-context services and messaging stores use that runtime database.

Backend selection occurs once in infrastructure composition. Backend-specific drivers, compilers, value mappings, connection behavior, and migrations remain under the corresponding infrastructure driver package. PostgreSQL is a future sibling driver and is not part of this implementation.

Bounded contexts own their neutral store ports, schemas, codecs, and services. They depend on the persistence kernel but never on infrastructure drivers.

The [supporting detail](supporting/persistence-boundaries.md) preserves the accepted constraints and verification requirements that accompany this decision.

## Context and rationale

Umbod must preserve its in-memory and SQLite behavior while making PostgreSQL possible without exposing backend details to domain, REST, or MCP modules.

The current persistence kernel provides neutral database ports and a typed DSL, but composition is incomplete. Some REST and MCP modules still inspect backend configuration, pass SQLite paths, instantiate SQLite adapters, or create persistence resources outside the application-scoped runtime. Migration execution is also distributed across store constructors, and messaging remains a separate path-based persistence stack.

The source tree must make the intended dependency direction visible and mechanically enforceable.

## Alternatives considered

An alternatives evaluation was not recorded. The context describes the competing pressures, but does not establish which alternatives were seriously considered or their full trade-offs.

## Consequences

### Positive

- Folder placement communicates backend-neutral and backend-specific responsibilities.
- PostgreSQL can be added as a sibling adapter without modifying domain stores.
- REST and MCP cannot accidentally select different backends within one application.
- In-memory state remains stable for the application lifetime.
- Migration behavior has one explicit owner.
- Architecture tests can enforce dependency direction and prohibit path-based store construction.

### Negative

- Existing compatibility constructors and path-based factories must be removed or converted.
- Messaging requires careful migration because its SQLite sequence semantics are observable behavior.
- Tests that instantiate concrete stores must explicitly construct and inject a database.
- Existing migration entry points must be consolidated without losing legacy data compatibility.

## Confidence and reevaluation

Confidence and decision date were not recorded. PostgreSQL compatibility remains a future obligation, not a verified result. Reevaluate through a new ADR if a new driver cannot satisfy the neutral contracts or application-lifetime rules. Earlier lifetime amendments involving ADR-008 require lifecycle confirmation; this formatting pass preserves the existing text.

## Supporting material

- [Accepted constraints and supporting detail](supporting/persistence-boundaries.md)

- [ADR-006: Filesystem Storage Infrastructure Boundary](ADR-006-filesystem-infrastructure-boundary.md)
- [ADR-008: Event-Synchronized In-Memory Tool Runtime](ADR-008-event-synchronized-tool-runtime.md)
