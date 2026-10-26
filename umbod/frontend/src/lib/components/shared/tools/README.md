# Shared tool presentation

**Module responsibility:** Actor-independent tool card structure, replaceable presentation sections, neutral display types, and schema formatting.

- `ToolCard.svelte` presents tool identity and card layout. Optional typed snippets supply description, parameters, output schema, and controls; omitted sections render no defaults.
- `ToolDescription.svelte` offers a compact description disclosure that actor compositions may select or replace.
- `ToolParameterDetails.svelte` renders parameter summaries and an optional full read-only input schema.
- `ToolOutputSchemaDetails.svelte` renders a declared output schema or its explicit absence.
- `presentation.ts` defines neutral parameter and output-schema display types.
- `json-schema-tool-parameters.ts` maps JSON Schema properties into neutral parameter display data; its specification tests preserve the existing mapping behavior.

Administration composes these through `../../admin/connectors/ToolCard.svelte`; Dashboard composes them through `../../dashboard/CatalogueToolCard.svelte`. Actor-specific data mapping, disclosure choices, and action policy stay in those compositions. Shared presenters never import actor models, controllers, or clients. Choosing the same presenter is deliberate reuse, not a requirement that actors always use identical content.

The cross-actor composition and dependency contracts are verified by `../../../acceptance/tool-card-composition.test.ts`. Follow the composition principle in `../../README.md` and [ADR-007](../../../../../../project/architecture-records/ADR-007-actor-specific-ui-composition.md).
