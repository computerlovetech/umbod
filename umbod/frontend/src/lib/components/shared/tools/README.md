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
- [ToolDescription.svelte](./ToolDescription.svelte) — Compact description preview and full-text disclosure.
- [ToolOutputSchemaDetails.svelte](./ToolOutputSchemaDetails.svelte) — Declared output schema in a shared disclosure, with a warning when no schema is declared.
- [ToolParameterDetails.svelte](./ToolParameterDetails.svelte) — Parameter summary, details, and nested read-only input schema disclosure.
- [tool-disclosures.dom.test.ts](./tool-disclosures.dom.test.ts) — Description preview and nested input schema interaction tests.

# Context not available from the code

- [ADR-007: Actor-Specific Composition](../../../../../../project/architecture-records/ADR-007-actor-specific-ui-composition.md) — Administration and Dashboard choose their own presenters and actions.
- [Composition acceptance tests](../../../acceptance/tool-card-composition.test.ts) — Cross-actor dependency constraints.
