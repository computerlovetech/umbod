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
- [endpoint_access.py](./endpoint_access.py) — Pre-registration access checks that distinguish anonymous initialization from OAuth evidence.
- [errors.py](./errors.py) — Connector failures.
- [management/](./management/) — Aggregate lifecycle and discovery.
- [models.py](./models.py) — Definitions and creation commands.
- [oauth/](./oauth/README.md) — Shared authorization and injected session boundaries.
- [permissions.py](./permissions.py) — Personal connector permission targets.
- [personal/](./personal/README.md) — Owner-scoped connections, OAuth workflows and private tool execution.
- [probe/](./probe/) — Shared discovery.
- [publishing/](./publishing/) — Namespace publication.
- [runtime/](./runtime/) — Shared runtime resolution.
- [security.py](./security.py) — Connector security policy.
- [stores/](./stores/README.md) — Persistence, credential-free owner discovery and atomic discovery notifications.
- [personal_refresh.py](./stores/personal_refresh.py) — Refresh transitions atomically update owner availability and connector-wide events, including committed uncertainty.
- [user_catalogue.py](./user_catalogue.py) — User-facing catalogue projections.
