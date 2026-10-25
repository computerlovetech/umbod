# ADR-006: Filesystem Storage Infrastructure Boundary

## Status

Accepted; amended for database-backed namespace and policy storage.

## Context

ADR-001 established backend-neutral persistence ports in core and concrete persistence drivers with backend selection in infrastructure. Its target structure and architecture checks restricted infrastructure to persistence composition and drivers.

The filesystem introduced separate namespace and content ports, a coordinating service, shared namespace rules, and production in-memory/local storage adapters. Its concrete adapters and configured factory initially lived inside the core feature package to satisfy the persistence-only infrastructure allowlist. This placed host-filesystem concerns and backend-selection configuration inside core.

The initial boundary placed concrete filesystem storage alongside persistence infrastructure while retaining independent namespace/content selection. A subsequent accepted change replaces the JSON and standalone in-memory namespace implementations with database-neutral stores using existing persistence drivers and adds ownership/sharing persistence. Content storage remains independent.

## Decision

Extend the explicit infrastructure boundary to include filesystem storage composition and drivers under `umbod.infrastructure.filesystem`, alongside `umbod.infrastructure.persistence`.

Core retains filesystem domain models, namespace/content/access-control ports, error vocabulary, shared hierarchy/name/revision rules, and the Filesystem application service. As in other ADR-001 bounded contexts, core also owns typed filesystem table declarations and database-neutral namespace/policy store services over the Database port. These are domain stores, not concrete database drivers. Core neither imports infrastructure nor owns host filesystem operations, local directory configuration, database backend selectors, or concrete byte-storage implementations.

Persistence infrastructure owns the existing in-memory and SQLite database drivers, transaction handling, and schema readiness. Filesystem infrastructure owns in-memory/local content drivers, immutable object publication, host-path validation, fsync, cancellation-safe byte I/O helpers, content backend configuration, and configured service/store composition. These implementations depend inward on core contracts and rules. The former JSON namespace driver, snapshot locking, and standalone in-memory namespace implementation are removed.

Database backend selection is consumed through the existing application's persistence runtime. Callers supply its Database explicitly to create_filesystem alongside FilesystemConfig, which selects content storage only. create_namespace_driver and create_access_control_driver consume that same injected Database; create_content_driver retains independent content selection. Factories never create a private database/runtime, prepare schemas, or assume ownership of runtime shutdown. Retired namespace configuration is rejected rather than silently ignored.

The public `umbod.infrastructure` package exports only approved composition functions and configuration values in addition to its existing persistence runtime surface. It does not export concrete filesystem driver classes. Applications and shared tests import that public root rather than reaching into driver packages. Driver-specific tests may directly import implementation modules from their dedicated `tests/umbod/infrastructure/filesystem` location.

Importing core must not load infrastructure. Importing infrastructure composition must not eagerly load concrete filesystem drivers or their POSIX-only dependencies. Concrete filesystem drivers are loaded when their declared backend is selected.

No compatibility module or re-export remains at the former core adapter/configuration paths. External composition callers migrate to the infrastructure root; domain callers retain their core contracts unchanged.

## Lifecycle And Behavior

Each composition call creates fresh operation/store objects over the supplied Database. Namespace and policy state is shared through that database; fresh store objects do not reset it. In-memory content is retained only by retaining its adapter instance; local content reopens the configured directory. Hosts retain the concurrency-safe persistence runtime for its intended lifetime, await schema readiness, and construct request-operation services through dependency providers. Filesystem tables join the existing application readiness registry; constructors perform no schema I/O. This ADR does not add services to app.state or wire filesystem REST/MCP operations.

The initial relocation preserved the JSON namespace format. The database amendment deliberately retires it: no implicit import/migration is performed, and existing JSON files are not deleted. SQLite reopening and serialized database transactions replace namespace lock/snapshot behavior. Local content retains immutable keys, publication order, cancellation-safe byte I/O, and POSIX/trusted-directory assumptions.

Namespace nodes, ownership, and grants share the application's neutral persistence database, following ADR-001. Per-node rows replace whole-namespace snapshots. Serialized-write sessions cover root provisioning and mutation validation/publication. Namespace and policy ports remain separate; node creation does not assign ownership. Policy persistence accepts logical node UUIDs independently of namespace existence, with exact principal identity, complete grant replacement, and last-applied owner replacement. Authorization evaluation and combined node/owner transactions remain deferred.

File bytes remain behind ContentDriver. Database transactions do not include local/object-store publication; content must be stored before its reference is published, and unreferenced bytes are not eagerly deleted.

## Enforcement

- Keep the exact infrastructure source-package allowlist: persistence and filesystem, plus the root package.
- Keep an exact public infrastructure export allowlist containing approved runtime/composition/configuration symbols only.
- Keep the prohibition against core importing infrastructure and against external deep infrastructure imports.
- Prohibit concrete filesystem driver exports at the infrastructure root.
- Assert absence of old core adapter/configuration locations and host filesystem imports in neutral filesystem modules.
- Use fresh-process import checks for core isolation and lazy infrastructure driver loading.
- Run shared namespace/policy contracts against both existing database drivers; preserve independent content adapter coverage.
- Verify SQLite reopening, concurrent transactions, and process-safe namespace mutation; retire JSON-specific tests rather than preserving dead implementations.
- Keep neutral store behavior tests at public protocol boundaries. Retain concrete driver/content-specific checks under approved infrastructure test boundaries.

## Consequences

Backend-neutral filesystem behavior and low-level host I/O now have a visible, mechanically enforced boundary matching the persistence dependency direction. Adding another storage driver does not require changing the domain service or importing infrastructure into core.

Composition/configuration import paths change deliberately; no compatibility bridge hides the old boundary. Architecture tests must extend their explicit infrastructure allowlists rather than adding broad exemptions or replacing exact checks with subset assertions.

This remains a scoped filesystem storage decision. It does not relocate connector-specific protocol adapters, replace existing downstream-MCP boundaries, generalize all I/O into infrastructure, introduce new database drivers, or add filesystem application entrypoints. Ownership/sharing persistence does not provide authentication, group resolution, inherited-grant evaluation, or authorization enforcement.
