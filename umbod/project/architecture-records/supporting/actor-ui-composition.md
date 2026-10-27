# Actor-Specific Composition of Shared UI Components — supporting detail

Preserved from [ADR-007: Actor-Specific Composition of Shared UI Components](../ADR-007-actor-specific-ui-composition.md). These details remain part of the accepted record; relocation does not change their authority or claim that implementation or verification is complete.

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
