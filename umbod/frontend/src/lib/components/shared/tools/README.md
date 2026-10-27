---
type: Software Module
title: "Shared tool presentation"
description: "Neutral tool cards, replaceable presenters and schema display formatting."
---

# Files

- [json-schema-tool-parameters.spec.ts](./json-schema-tool-parameters.spec.ts) — Schema-to-display mapping tests.
- [json-schema-tool-parameters.ts](./json-schema-tool-parameters.ts) — Parameter display mapping.
- [presentation.ts](./presentation.ts) — Neutral schema display types.
- [ToolCard.svelte](./ToolCard.svelte) — Tool card layout and snippet slots.
- [ToolDescription.svelte](./ToolDescription.svelte) — Description disclosure.
- [ToolOutputSchemaDetails.svelte](./ToolOutputSchemaDetails.svelte) — Declared output schema display.
- [ToolParameterDetails.svelte](./ToolParameterDetails.svelte) — Input parameter and schema display.

# Context not available from the code

- [ADR-007: Actor-Specific Composition](../../../../../../project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Administration and Dashboard choose their own presenters and actions.
- [Composition acceptance tests](../../../acceptance/tool-card-composition.test.ts) — Cross-actor dependency constraints.
