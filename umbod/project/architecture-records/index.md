# Architecture decisions

Records are accepted unless marked **Proposed**. Two records share the number ADR-009; use their titles or file paths to distinguish them.

## Backend boundaries and developer tooling

- [ADR-003: Umbod connector CLI](./ADR-003-umbod-specific-connector-cli.md) — Connector development commands and SDK CLI scope.
- [ADR-004: One backend API and a thin Desktop boundary](./ADR-004-single-backend-api-and-desktop-boundary.md) — Backend API ownership and Desktop integration.
- [ADR-013: Signal-owned logging and side effects](./ADR-013-signal-owned-application-logging.md) — Application diagnostics and optional effects such as logging, metrics, and audit observation.

## Persistence, storage, and data access

- [ADR-001: Backend-neutral persistence](./ADR-001-backend-neutral-persistence.md) — Database boundaries, migrations, and persistence runtime lifetimes.
- [ADR-006: Filesystem infrastructure boundary](./ADR-006-filesystem-infrastructure-boundary.md) — File storage, namespaces, ownership, and byte I/O.
- [ADR-009: Explicit deferred read planning](./ADR-009-deferred-read-planning.md) — Deferred persistence reads and request-scoped read plans.
- [ADR-009: Transport-neutral file upload sessions](./ADR-009-transport-neutral-upload-sessions.md) — Upload sessions, transfer instructions, and file publication across REST and MCP.
- [ADR-010: Key-value storage and request caching](./ADR-010-key-value-storage-drivers.md) — Storage driver boundaries, cache coordination, and invalidation.

## Workspace and UI

- [ADR-005: One workspace and only usable controls](./ADR-005-unified-workspace-and-usable-controls.md) — Navigation and control eligibility.
- [ADR-007: Actor-specific UI composition](./ADR-007-actor-specific-ui-composition.md) — Shared components and actor-owned views.
- [ADR-011: State ownership and rendering boundaries](./ADR-011-state-ownership-and-rendering-boundaries.md) — UI state, derived values, event handling, and state lifetimes.

## MCP credentials, discovery, and tool contracts

- [ADR-002: Client-owned MCP credentials](./ADR-002-client-side-credential-storage.md) — **Proposed.** Provider credential ownership and authentication.
- [ADR-008: Event-synchronized tool runtime](./ADR-008-event-synchronized-tool-runtime.md) — Tool registration, discovery, routing, synchronization, and invocation.
- [ADR-012: Permission-aware MCP tool visibility](./ADR-012-permission-aware-mcp-tool-visibility.md) — **Proposed.** Caller-specific discovery and partially authorized tools.
- [ADR-014: Built-in tool responses and agent guidance](./ADR-014-built-in-mcp-response-guidance.md) — Response DTOs, content and metadata, extensions, confirmation, and elicitation.
- [ADR-015: Self-describing built-in tool contracts](./ADR-015-self-describing-built-in-mcp-tool-contracts.md) — Input schemas, discovery descriptions, and client rendering compatibility.
