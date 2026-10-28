---
type: Software Module
title: "Downstream MCP connectors"
description: "Shared and personal downstream MCP connector coordination."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [activation/](./activation/) — Connector activation.
- [adapters/](./adapters/README.md) — Protocol and configuration integration.
- [catalog/](./catalog/) — Shared capability projections.
- [connection.py](./connection.py) — Shared connection integration.
- [errors.py](./errors.py) — Connector failures.
- [management/](./management/) — Aggregate lifecycle and discovery.
- [models.py](./models.py) — Definitions and creation commands.
- [oauth/](./oauth/README.md) — Shared authorization and injected session boundaries.
- [permissions.py](./permissions.py) — Personal connector permission targets.
- [personal_connections/](./personal_connections/README.md) — Owner-bound connection lifecycle.
- [personal_oauth_configuration/](./personal_oauth_configuration/README.md) — Personal OAuth policy, separate from shared connector authority.
- [personal_tools/](./personal_tools/README.md) — Owner-bound private inventories and execution.
- [probe/](./probe/) — Shared discovery.
- [publishing/](./publishing/) — Namespace publication.
- [runtime/](./runtime/) — Shared runtime resolution.
- [security.py](./security.py) — Connector security policy.
- [stores/](./stores/) — Connector persistence.
- [user_catalogue.py](./user_catalogue.py) — User-facing catalogue projections.

# Related links

- [Foundation specification](../../../../../../docs/operations/personal-downstream-mcp-oauth-specification.md) — Personal ownership and authorization boundaries.
- [Catalogue specification](../../../../../../docs/operations/personal-downstream-mcp-catalogue-specification.md) — Personal selection and catalogue scope.
- [Authorization specification](../../../../../../docs/operations/personal-downstream-mcp-authorization-specification.md) — Durable personal sign-in scope.
