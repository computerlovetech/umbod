# ADR-004: One Backend API and a Thin Desktop Boundary

- **Status:** Accepted
- **Date:** 2026-10-12
- **Decision owners:** Architecture / Platform
- **Scope:** Umbod backend and macOS Desktop

## Decision

Umbod has **one backend implementation and one backend API**, owned by `umbod/api`. Every client, including Desktop, uses the same product contracts.

Reusable domain and application behavior must be implemented there and exposed through the shared API. This includes connector lifecycle, authentication discovery and orchestration, authorization state, permissions, publication, diagnostics, and product-level error semantics.

Desktop is a client and platform adapter for that backend. Desktop-only backend code is permitted only for behavior that is inherently local to the macOS host, such as:

- Opening a browser and transporting a loopback callback to the shared backend.
- Storing credentials in macOS Keychain through shared storage contracts.
- Managing the bundled process, installation, and application lifecycle.
- Transporting the shared API contract over local IPC without adding private routes, commands, or semantics.
- Mapping shared API contracts into native SwiftUI presentation state.
- Performing one-way, idempotent compatibility migrations from earlier Desktop formats. Each migration must have an explicit completion or removal criterion and must not provide steady-state product behavior.

Protocol validation, token exchange and refresh, failure classification, and resulting authentication state belong to the shared backend.

A capability that could be used by the web administration client, another native client, or a server deployment belongs in `umbod/api`, even when Desktop is its first consumer. Desktop must call or adapt the shared capability rather than implement a parallel workflow or private product API.

### Immediate boundary correction

Shared OAuth discovery, registration-mode decisions, scope summaries, status transitions, safe failure categories, diagnostics, and the distinction between authorization failure and connector-discovery failure belong in the shared backend.

Desktop retains browser launch, loopback callback transport, Keychain integration, and native presentation. Existing Desktop OAuth orchestration that exceeds this boundary must be moved into the shared backend before further Desktop-only product behavior is added.

## Context and rationale

Umbod Desktop embeds the shared Python backend and adds a native SwiftUI client. Recent Desktop work correctly reused the shared connector, permission, persistence, and OAuth foundations, but also placed reusable OAuth discovery and orchestration behavior in the Desktop host.

If reusable application behavior continues to accumulate under `desktop/`, Umbod will effectively maintain a second backend with different features and semantics.

## Alternatives considered

An alternatives evaluation was not recorded. The context describes the competing pressures, but does not establish which alternatives were seriously considered or their full trade-offs.

## Consequences

- Backend behavior remains consistent across clients and deployments.
- Desktop stays independently packageable without becoming a second product backend.
- Shared features may require host-facing ports for browser callbacks, credential storage, and lifecycle events.
- Platform adapters can differ, but domain rules, state models, and API semantics cannot.
- Reviews must reject new Desktop-only backend behavior unless the change is demonstrably macOS-specific or a bounded compatibility migration.

## Confidence and reevaluation

Confidence was not recorded. The context records a risk of diverging backend behavior, not measured implementation results. Reevaluate through a new ADR if a client requires product semantics that cannot be expressed through the shared backend and its host-facing ports.

## Supporting material

- [ADR-001: Backend-Neutral Persistence Module Boundaries](ADR-001-backend-neutral-persistence.md)
