# ADR-006: Filesystem Storage Infrastructure Boundary

- **Status:** Accepted
- **Date:** Not recorded
- **Scope:** Filesystem domain, storage composition, and namespace/policy persistence

## Decision

Extend the explicit infrastructure boundary to include filesystem storage composition and drivers under `umbod.infrastructure.filesystem`, alongside `umbod.infrastructure.persistence`.

Core retains filesystem domain models, namespace/content/access-control ports, error vocabulary, shared hierarchy/name/revision rules, and the Filesystem application service. As in other ADR-001 bounded contexts, core also owns typed filesystem table declarations and database-neutral namespace/policy store services over the Database port. These are domain stores, not concrete database drivers. Core neither imports infrastructure nor owns host filesystem operations, local directory configuration, database backend selectors, or concrete byte-storage implementations.

Persistence infrastructure owns the existing in-memory and SQLite database drivers, transaction handling, and schema readiness. Filesystem infrastructure owns in-memory/local content drivers, immutable object publication, host-path validation, fsync, cancellation-safe byte I/O helpers, content backend configuration, and configured service/store composition. These implementations depend inward on core contracts and rules. The former JSON namespace driver, snapshot locking, and standalone in-memory namespace implementation are removed.

Database backend selection is consumed through the existing application's persistence runtime. Callers supply its Database explicitly to create_filesystem alongside FilesystemConfig, which selects content storage only. create_namespace_driver and create_access_control_driver consume that same injected Database; create_content_driver retains independent content selection. Factories never create a private database/runtime, prepare schemas, or assume ownership of runtime shutdown. Retired namespace configuration is rejected rather than silently ignored.

The public `umbod.infrastructure` package exports only approved composition functions and configuration values in addition to its existing persistence runtime surface. It does not export concrete filesystem driver classes. Applications and shared tests import that public root rather than reaching into driver packages. Driver-specific tests may directly import implementation modules from their dedicated `tests/umbod/infrastructure/filesystem` location.

Importing core must not load infrastructure. Importing infrastructure composition must not eagerly load concrete filesystem drivers or their POSIX-only dependencies. Concrete filesystem drivers are loaded when their declared backend is selected.

No compatibility module or re-export remains at the former core adapter/configuration paths. External composition callers migrate to the infrastructure root; domain callers retain their core contracts unchanged.

The [supporting detail](supporting/filesystem-boundaries.md) preserves the accepted constraints and verification requirements that accompany this decision.

## Context and rationale

ADR-001 established backend-neutral persistence ports in core and concrete persistence drivers with backend selection in infrastructure. Its target structure and architecture checks restricted infrastructure to persistence composition and drivers.

The filesystem introduced separate namespace and content ports, a coordinating service, shared namespace rules, and production in-memory/local storage adapters. Its concrete adapters and configured factory initially lived inside the core feature package to satisfy the persistence-only infrastructure allowlist. This placed host-filesystem concerns and backend-selection configuration inside core.

The initial boundary placed concrete filesystem storage alongside persistence infrastructure while retaining independent namespace/content selection. A subsequent accepted change replaces the JSON and standalone in-memory namespace implementations with database-neutral stores using existing persistence drivers and adds ownership/sharing persistence. Content storage remains independent.

## Alternatives considered

An alternatives evaluation was not recorded. The context describes the competing pressures, but does not establish which alternatives were seriously considered or their full trade-offs.

## Consequences

Backend-neutral filesystem behavior and low-level host I/O now have a visible, mechanically enforced boundary matching the persistence dependency direction. Adding another storage driver does not require changing the domain service or importing infrastructure into core.

Composition/configuration import paths change deliberately; no compatibility bridge hides the old boundary. Architecture tests must extend their explicit infrastructure allowlists rather than adding broad exemptions or replacing exact checks with subset assertions.

This remains a scoped filesystem storage decision. It does not relocate connector-specific protocol adapters, replace existing downstream-MCP boundaries, generalize all I/O into infrastructure, introduce new database drivers, or add filesystem application entrypoints. Ownership/sharing persistence does not provide authentication, group resolution, inherited-grant evaluation, or authorization enforcement.

## Confidence and reevaluation

Confidence and decision date were not recorded. The record describes an accepted database amendment but supplies no dated supersession history; that lifecycle gap requires owner confirmation, not an inferred approval. Reevaluate through a new ADR if content publication must be atomic with database state or the storage boundary changes.

## Supporting material

- [Accepted constraints and supporting detail](supporting/filesystem-boundaries.md)

- [ADR-001: Backend-Neutral Persistence Module Boundaries](ADR-001-backend-neutral-persistence.md)
