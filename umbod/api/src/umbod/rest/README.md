---
type: Software Module
title: "REST boundary"
description: "FastAPI delivery for administration, authenticated users, system endpoints and telemetry."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [admin_overview/](./admin_overview/README.md) — Overview metadata summary.
- [authentication/](./authentication/) — Authentication and cookie safeguards.
- [capability_descriptions/](./capability_descriptions/) — Description overrides.
- [connectors/](./connectors/) — Connector administration and personal delivery.
- [dependencies.py](./dependencies.py) — Shared dependency providers.
- [factories.py](./factories.py) — Adapter composition.
- [filesystem/](./filesystem/README.md) — User filesystem browsing, creation, uploads and downloads.
- [filesystem_administration/](./filesystem_administration/README.md) — Root-access administration.
- [groups/](./groups/README.md) — Group catalogue administration.
- [instance_configuration/](./instance_configuration/) — Client-visible instance settings.
- [main.py](./main.py) — Application assembly and mounts.
- [mcp_permissions/](./mcp_permissions/README.md) — Group-to-capability permissions.
- [metrics/](./metrics/) — API instrumentation.
- [proxies.py](./proxies.py) — Deferred bindings.
- [settings.py](./settings.py) — REST settings.
- [system/](./system/) — Internal state, events and health.
- [telemetry/](./telemetry/README.md) — OTLP receiver.
- [user_catalogue/](./user_catalogue/README.md) — Cross-kind user catalogue.
- [users/](./users/) — Current-user identity and profile enrichment.

# Related links

- [Hosting boundary](../hosting/README.md) — Supported composition API.
- [Operator configuration](../../../../docs/operations/configuration.md) — Gateway authentication and user-profile deployment requirements.
- [Personal authorization specification](../../../../docs/operations/personal-downstream-mcp-authorization-specification.md) — Personal credential and public callback boundary.
