# ADR-006: Filesystem Storage Infrastructure Boundary

## Status

Accepted

## Context

ADR-001 established backend-neutral persistence ports in core and concrete persistence drivers with backend selection in infrastructure. Its target structure and architecture checks restricted infrastructure to persistence composition and drivers.

The filesystem introduced separate namespace and content ports, a coordinating service, shared namespace rules, and production in-memory/local storage adapters. Its concrete adapters and configured factory initially lived inside the core feature package to satisfy the persistence-only infrastructure allowlist. This placed host-filesystem concerns and backend-selection configuration inside core.

The requested boundary places concrete filesystem storage alongside persistence infrastructure while retaining independent namespace/content selection and the existing public service behavior.

## Decision

Extend the explicit infrastructure boundary to include filesystem storage composition and drivers under `umbod.infrastructure.filesystem`, alongside `umbod.infrastructure.persistence`.

Core retains filesystem domain models, namespace/content ports, error vocabulary, shared hierarchy/name/revision rules, and the Filesystem application service. Core neither imports infrastructure nor owns host filesystem operations, local directory configuration, backend selectors, or concrete storage implementations.

Infrastructure owns in-memory and local namespace/content drivers, file locking, JSON snapshot persistence, object publication, host-path validation, fsync, cancellation-safe I/O helpers, declared backend configuration, and configured service composition. These implementations depend inward on core contracts and rules.

Backend selection is consumed at the outer composition boundary. Callers supply FilesystemConfig and use create_filesystem to obtain the configured service. Namespace and content choices remain independent. Separate create_namespace_driver and create_content_driver factories support infrastructure lifetime ownership and service injection.

The public `umbod.infrastructure` package exports only approved composition functions and configuration values in addition to its existing persistence runtime surface. It does not export concrete filesystem driver classes. Applications and shared tests import that public root rather than reaching into driver packages. Driver-specific tests may directly import implementation modules from their dedicated `tests/umbod/infrastructure/filesystem` location.

Importing core must not load infrastructure. Importing infrastructure composition must not eagerly load concrete filesystem drivers or their POSIX-only dependencies. Concrete filesystem drivers are loaded when their declared backend is selected.

No compatibility module or re-export remains at the former core adapter/configuration paths. External composition callers migrate to the infrastructure root; domain callers retain their core contracts unchanged.

## Lifecycle And Behavior

Each composition call creates fresh adapter instances. In-memory state is shared only when callers retain the intended storage instances. Local adapters reopen the same configured directories. Future request-scoped hosts retain concurrency-safe infrastructure dependencies for their intended lifetime and construct request-operation services through dependency providers; this ADR does not add services to app.state or wire REST/MCP.

The relocation preserves the local namespace format, immutable content keys, publication order, interprocess synchronization, cancellation semantics, and POSIX/trusted-directory assumptions. It introduces no storage migration or new filesystem feature.

Namespace/content storage remains separate from the application persistence database. This extension does not weaken ADR-001's requirement that database-backed bounded contexts share their application's neutral persistence runtime.

## Enforcement

- Keep the exact infrastructure source-package allowlist: persistence and filesystem, plus the root package.
- Keep an exact public infrastructure export allowlist containing approved runtime/composition/configuration symbols only.
- Keep the prohibition against core importing infrastructure and against external deep infrastructure imports.
- Prohibit concrete filesystem driver exports at the infrastructure root.
- Assert absence of old core adapter/configuration locations and host filesystem imports in neutral filesystem modules.
- Use fresh-process import checks for core isolation and lazy infrastructure driver loading.
- Run unchanged behavioral contracts against both backends and retain local-only persistence, failure, cancellation, and process tests under the infrastructure test boundary.

## Consequences

Backend-neutral filesystem behavior and low-level host I/O now have a visible, mechanically enforced boundary matching the persistence dependency direction. Adding another storage driver does not require changing the domain service or importing infrastructure into core.

Composition/configuration import paths change deliberately; no compatibility bridge hides the old boundary. Architecture tests must extend their explicit infrastructure allowlists rather than adding broad exemptions or replacing exact checks with subset assertions.

This is a scoped extension for filesystem storage. It does not relocate connector-specific protocol adapters, replace existing downstream-MCP boundaries, generalize all I/O into infrastructure, add authorization/storage backends, or introduce application wiring.
