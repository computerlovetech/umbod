---
type: Software Module
title: "Administration"
description: "Administration contracts, browser clients and feature state for connector and permission management."
---

# Files

- [capability-catalogs.ts](./capability-catalogs.ts) — Prompt and resource catalogue contracts.
- [capability-catalogs.spec.ts](./capability-catalogs.spec.ts) — Catalogue contract tests.
- [capability-descriptions-api.ts](./capability-descriptions-api.ts) — Capability description HTTP adapter.
- [capability-descriptions-browser-api.ts](./capability-descriptions-browser-api.ts) — Browser description client.
- [capability-descriptions.ts](./capability-descriptions.ts) — Capability description models.
- [capability-descriptions.spec.ts](./capability-descriptions.spec.ts) — Description contract tests.
- [clipboard.ts](./clipboard.ts) — Clipboard interaction.
- [connector-capabilities.ts](./connector-capabilities.ts) — Capability selection and URL helpers.
- [connector-capabilities.test.ts](./connector-capabilities.test.ts) — Capability navigation tests.
- [connector-details-browser-api.ts](./connector-details-browser-api.ts) — Native connector detail client.
- [connectors.ts](./connectors.ts) — Native connector and tool models.
- [connectors-api.ts](./connectors-api.ts) — Native connector HTTP adapter.
- [connectors-api.spec.ts](./connectors-api.spec.ts) — Native connector API tests.
- [connectors-forms.ts](./connectors-forms.ts) — Native connector form validation.
- [downstream-mcp-connectors.ts](./downstream-mcp-connectors.ts) — Shared and Personal MCP models.
- [downstream-mcp-connectors.spec.ts](./downstream-mcp-connectors.spec.ts) — MCP contract tests.
- [downstream-mcp-connectors-api.ts](./downstream-mcp-connectors-api.ts) — MCP administration HTTP adapter.
- [downstream-mcp-errors.ts](./downstream-mcp-errors.ts) — MCP failure presentation.
- [downstream-mcp-errors.spec.ts](./downstream-mcp-errors.spec.ts) — MCP failure tests.
- [group-permissions.ts](./group-permissions.ts) — Connector grant models.
- [group-permissions-api.ts](./group-permissions-api.ts) — Connector permissions HTTP adapter.
- [group-permissions-api.spec.ts](./group-permissions-api.spec.ts) — Permissions API tests.
- [group-permissions-forms.ts](./group-permissions-forms.ts) — Permission form validation.
- [instance-configuration.ts](./instance-configuration.ts) — Instance settings contracts.
- [instance-configuration-api.ts](./instance-configuration-api.ts) — Instance settings HTTP adapter.
- [instance-configuration-api.spec.ts](./instance-configuration-api.spec.ts) — Instance settings API tests.
- [invocation-policy.ts](./invocation-policy.ts) — Tool invocation policy contracts.
- [openapi-connector-details-browser-api.ts](./openapi-connector-details-browser-api.ts) — OpenAPI detail client.
- [openapi-connector-tools-browser-api.ts](./openapi-connector-tools-browser-api.ts) — OpenAPI tool client.
- [openapi-connectors.ts](./openapi-connectors.ts) — OpenAPI connector models.
- [openapi-connectors-api.ts](./openapi-connectors-api.ts) — OpenAPI administration HTTP adapter.
- [openapi-connectors-api.spec.ts](./openapi-connectors-api.spec.ts) — OpenAPI API tests.
- [openapi-setup.ts](./openapi-setup.ts) — OpenAPI setup contracts.
- [selected-detail-facade.ts](./selected-detail-facade.ts) — Workspace detail selection and failures.
- [selected-detail-facade.test.ts](./selected-detail-facade.test.ts) — Selected detail tests.
- [tool-activation-capability.ts](./tool-activation-capability.ts) — Tool activation save port.
- [tool-activation-reconciliation.ts](./tool-activation-reconciliation.ts) — Authoritative save-failure presentation.
- [tool-activation-reconciliation.test.ts](./tool-activation-reconciliation.test.ts) — Save reconciliation tests.
- [tool-output-schema.ts](./tool-output-schema.ts) — Declared output schema normalization.
- [tool-output-schema.test.ts](./tool-output-schema.test.ts) — Output schema tests.
- [filesystem](./filesystem/README.md) — Root filesystem access administration.
- [groups](./groups/README.md) — Shared group catalogue.
- [infrastructure](./infrastructure/README.md) — Transport and API composition.
- [operations](./operations/README.md) — Browser mutation dispatch.
- [overview](./overview/README.md) — Administration overview aggregation.
- [personal-mcp-servers/](./personal-mcp-servers/) — Personal server registration and policy.
