# ADR-011: State Ownership and Rendering Boundaries

- **Status:** Accepted
- **Date:** 2026-10-30
- **Scope:** Interactive user interfaces; Svelte conventions apply to the web application

## Decision

Mutable state, derived values, and state transitions belong in cohesive state classes with explicit public methods and read-only outputs.

Rendering components consume those outputs and forward user actions to state methods; they do not mutate state, duplicate business rules, or synchronize parallel copies of it.

## Ownership and public interfaces

Each state class owns one cohesive concern and its invariants. Compose state classes when a view combines independent concerns rather than creating a page-wide god class. State classes live outside rendering components and expose the values and operations their consumers actually need.

All writes to owned state go through named public methods, including changes caused by user input, dependency responses, subscriptions, and lifecycle events. Rendering code must not assign fields, mutate exposed collections or nested objects, or use two-way bindings to bypass those methods. A readonly property containing a mutable collection does not establish a read-only boundary; expose a read-only view, a lookup operation, or an isolated snapshot as appropriate.

Derived values have the same ownership boundary as mutable state. Filtering, selection, status reconciliation, eligibility, counts, and other computed view state belong with the state that determines them. Consumers read these outputs rather than rebuilding the same projections in components. Derived outputs follow their current inputs without maintaining a second mutable copy.

Templates retain declarative rendering, conditional sections, iteration, composition, and accessibility markup. Stateless presentation helpers may remain with shared presentation, as described in [ADR-007](ADR-007-actor-specific-ui-composition.md); they must not become a second owner of state or actor-specific policy.

## Dependencies and lifecycle

State classes coordinate application behavior through explicit dependencies at the owning composition boundary. Network, storage, navigation, and other external effects remain behind the applicable interfaces or adapters. Separating state from rendering does not move backend-owned rules into a client or change the shared API boundary established by [ADR-004](ADR-004-single-backend-api-and-desktop-boundary.md).

Composition creates state instances at the appropriate view or operation scope and owns their disposal. Components may wire mount, unmount, input, and DOM integration events to state methods. DOM references and imperative presentation mechanics remain scoped to the presentation concern that owns them, not unrelated domain state.

An operation's lifetime must not depend on an incidental menu, confirmation button, or form remaining mounted. State owns pending work, duplicate-submission protection, error handling, and reconciliation. Disposal, cancellation, selection changes, and access loss must fence obsolete results according to the operation's contract.

Successful operations reconcile validated authoritative results into the owning state. They must not force document navigation or remount unrelated rendering solely to refresh a status. Preserve selection, filters, and other unaffected interaction state unless the requested operation explicitly changes them. An explicit recovery reload after an uncertain outcome is a separate behavior, not the default success path.

## Svelte conventions

- Define reactive state classes in `.svelte.ts` modules, not inside `.svelte` components.
- Keep mutable runes and derived-state declarations in those classes. Components read class outputs and invoke methods rather than declaring parallel `$state` or `$derived` projections.
- Keep props and dependency inputs current through the supported reactive input contract. Do not copy them into independently writable state or introduce effects solely to synchronize copies.
- Prefer derived state to effect-driven mirroring. Reserve effects, subscriptions, and attachments for actual external integration, with explicit ownership and cleanup.
- Pass callbacks without losing the state instance's method context.

## Context and rationale

When state ownership is split between components and controllers, a rule can change in one place without updating another. Tests then need mounted rendering or source-text assertions to verify behavior that should be independently testable.

The MCP publication flow exposed both lifetime and ownership problems: removing a dropdown form prevented dispatch, while refreshing publication through document navigation discarded interaction state. Keeping a menu mounted or rebuilding the page hides those problems rather than establishing a stable owner for the operation and its results.

This decision complements actor-owned composition in [ADR-007](ADR-007-actor-specific-ui-composition.md) and control eligibility in [ADR-005](ADR-005-unified-workspace-and-usable-controls.md). Shared rendering remains actor-independent, while actor-owned state supplies current eligibility and presentation data. UI eligibility never replaces backend authorization.

## Verification

- Test state rules and transitions through public methods and read-only outputs with small injected fakes at external boundaries. Keep the state behavior under test real.
- Test rendering and interaction at the component boundary when event wiring, accessibility, reactivity, mounting, or disposal is the behavior under test. Do not bypass that boundary by calling controllers from an interaction test.
- Cover pending, success, failure, cancellation, access loss, and obsolete-result behavior where applicable. For in-place updates, verify authoritative status changes without losing unaffected interaction state or remounting the workspace.
- Keep architecture checks distinct from behavior tests. Source-text checks do not prove runtime state transitions or lifecycle behavior.

## Alternatives considered

- Component-owned mutable and derived state: locally convenient, but scatters ownership and couples behavioral tests to rendering.
- A single global store or page-wide state class: centralizes values, but combines unrelated lifetimes and responsibilities.
- Mirrored state synchronized by effects: creates competing sources of truth and ordering-sensitive updates.
- Permanent mounting or full-page reloads as reconciliation mechanisms: ties correctness to rendering lifetime or discards unrelated user state.

## Consequences and adoption

Rendering components become smaller, state behavior can be tested independently, and ownership remains explicit across asynchronous work. This requires deliberate public interfaces, reactive input contracts, and resource lifetimes; extracting fields into a class alone is not sufficient.

Apply this boundary to new stateful interfaces and when changing state ownership in existing interfaces. Migrate existing code in cohesive, behavior-preserving steps rather than combining this decision with an unrelated application-wide rewrite. This record establishes the required direction; it does not assert that existing components already conform.
