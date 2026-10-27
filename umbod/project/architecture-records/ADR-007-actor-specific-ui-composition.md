# ADR-007: Actor-Specific Composition of Shared UI Components

- **Status:** Accepted
- **Decision owners:** Product / Frontend architecture
- **Scope:** Umbod web components
- **Date:** Not recorded

## Decision

Share structural presentation and interaction mechanics while allowing the parent to supply sections that have different reasons to change. In Svelte, expose replaceable content through typed snippets and compose it in actor-owned components.

Shared components own layout, identity presentation, reusable rendering, and general accessibility behavior. They do not determine actor eligibility, authorize operations, fetch actor inventories, or depend on actor-specific controllers, API contracts, or administration models. Neutral presentation types and pure formatting helpers belong with the shared presentation they support.

Actor-owned compositions adapt their own data and choose descriptions, parameter and schema presentations, metadata, controls, and disclosure policies. Different actors may deliberately select the same neutral presenter; replace that selection in the actor-owned composition when their needs diverge. Do not add actor flags or duplicate whole shared components to accommodate a replaceable section.

A shared component change may intentionally affect every consumer. Such changes require verification of those consumers. Actor-specific changes should normally be possible by changing the actor-owned composition without modifying the shared layout or another actor's view. Moving a component to a shared directory without removing actor-specific responsibilities does not establish this boundary.

Do not introduce extension points solely for hypothetical variation. Small amounts of composition markup are acceptable duplication; business rules, validation, formatting mechanisms, and accessibility behavior should not be copied merely to create separate actor views.

The [supporting detail](supporting/actor-ui-composition.md) preserves the accepted constraints and verification requirements that accompany this decision.

## Context and rationale

[ADR-005](ADR-005-unified-workspace-and-usable-controls.md) establishes one consistent workspace with actor-eligible controls. A consistent appearance does not require administration and ordinary-user experiences to share every presentation decision.

Reusing a complete actor-owned view can make an unrelated actor change when its description, schema, status, or controls are changed. Duplicating entire cards, layouts, and interaction mechanics avoids that coupling but creates unnecessary maintenance and accessibility work.

## Alternatives considered

An alternatives evaluation was not recorded. The context describes the competing pressures, but does not establish which alternatives were seriously considered or their full trade-offs.

## Consequences

Actor-specific requirements can evolve without copying shared card structure or modifying another actor's composition. Reusable presenters and accessibility behavior remain implemented once. Shared visual changes still have a deliberate cross-consumer impact and must be checked accordingly.

This is a focused composition boundary, not a requirement to wrap every UI element, migrate every existing component immediately, duplicate business services, or prohibit deliberate shared styling.

## Confidence and reevaluation

Confidence and decision date were not recorded. The tool-card application and acceptance criteria describe the intended boundary, not evidence that checks passed. Reevaluate through a new ADR if actor-specific requirements cannot be composed without coupling shared presentation to actor-owned policy.

## Supporting material

- [Accepted constraints and supporting detail](supporting/actor-ui-composition.md)
