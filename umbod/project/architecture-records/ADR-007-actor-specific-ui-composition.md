# ADR-007: Actor-Specific Composition of Shared UI Components

- **Status:** Accepted
- **Decision owners:** Product / Frontend architecture
- **Scope:** Umbod web components

## Context

[ADR-005](ADR-005-unified-workspace-and-usable-controls.md) establishes one consistent workspace with actor-eligible controls. A consistent appearance does not require administration and ordinary-user experiences to share every presentation decision.

Reusing a complete actor-owned view can make an unrelated actor change when its description, schema, status, or controls are changed. Duplicating entire cards, layouts, and interaction mechanics avoids that coupling but creates unnecessary maintenance and accessibility work.

## Decision

Share structural presentation and interaction mechanics while allowing the parent to supply sections that have different reasons to change. In Svelte, expose replaceable content through typed snippets and compose it in actor-owned components.

Shared components own layout, identity presentation, reusable rendering, and general accessibility behavior. They do not determine actor eligibility, authorize operations, fetch actor inventories, or depend on actor-specific controllers, API contracts, or administration models. Neutral presentation types and pure formatting helpers belong with the shared presentation they support.

Actor-owned compositions adapt their own data and choose descriptions, parameter and schema presentations, metadata, controls, and disclosure policies. Different actors may deliberately select the same neutral presenter; replace that selection in the actor-owned composition when their needs diverge. Do not add actor flags or duplicate whole shared components to accommodate a replaceable section.

A shared component change may intentionally affect every consumer. Such changes require verification of those consumers. Actor-specific changes should normally be possible by changing the actor-owned composition without modifying the shared layout or another actor's view. Moving a component to a shared directory without removing actor-specific responsibilities does not establish this boundary.

Do not introduce extension points solely for hypothetical variation. Small amounts of composition markup are acceptable duplication; business rules, validation, formatting mechanisms, and accessibility behavior should not be copied merely to create separate actor views.

## Tool Card Application

`frontend/src/lib/components/shared/tools/ToolCard.svelte` owns the card structure and tool identity. Description, parameters, output schema, and controls are optional typed snippets. It supplies no implicit description, parameter summary, absent-schema warning, or management action.

The administration `ToolCard.svelte` composes administration data, default presenters, and caller-supplied management controls. Dashboard `CatalogueToolCard.svelte` composes the user catalogue, full execution input schema, output-schema projection, and no administrative controls. Both select neutral presenters under `components/shared/tools/` without importing each other's view or data models.

Existing administration wire-format normalization remains administration-owned. Shared presentation does not require a unified backend DTO, a new backend service, or changes to permission and owner-lifetime boundaries.

## Acceptance Criteria

- Shared tool presentation has no dependency on actor-owned modules.
- Callers can replace or omit description, input, output, and control sections independently.
- The shared card renders no role-specific defaults when sections are omitted.
- Administration retains its management controls and existing presentation behavior.
- Dashboard retains read-only schemas without inheriting administrative controls.
- Component tests cover independent section replacement, actor compositions, and the shared dependency boundary.
- Browser verification covers the affected views and responsive behavior without performing live authorization or management mutations.

## Consequences

Actor-specific requirements can evolve without copying shared card structure or modifying another actor's composition. Reusable presenters and accessibility behavior remain implemented once. Shared visual changes still have a deliberate cross-consumer impact and must be checked accordingly.

This is a focused composition boundary, not a requirement to wrap every UI element, migrate every existing component immediately, duplicate business services, or prohibit deliberate shared styling.
