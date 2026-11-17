---
type: Software Module
title: "REST boundary"
description: "FastAPI delivery for administration, authenticated users, system endpoints and telemetry."
---

# Files

- [__init__.py](./__init__.py) — Deferred package exports preserving original owner identities.
- [admin_overview/](./admin_overview/README.md) — Overview metadata summary.
- [agent_behaviour/](./agent_behaviour/README.md) — Published behaviour configuration and administrator-only self-report inspection.
- [authentication/](./authentication/) — Authentication and cookie safeguards.
- [capability_descriptions/](./capability_descriptions/) — Description overrides.
- [connectors/](./connectors/README.md) — Connector administration and personal delivery.
- [dependencies.py](./dependencies.py) — Shared dependency providers.
- [factories.py](./factories.py) — Adapter composition and lazy personal catalogue store wiring.
- [filesystem/](./filesystem/README.md) — User namespace browsing, item sharing, creation, uploads and downloads.
- [filesystem_administration/](./filesystem_administration/README.md) — Shared namespace administration.
- [groups/](./groups/README.md) — Group catalogue administration.
- [identity_directory/](./identity_directory/README.md) — Verified observation capture and administrative searches.
- [install/](./install/README.md) — Public instance-configured installer scripts and Codex/Claude Code package downloads.
- [instance_configuration/](./instance_configuration/) — Client-visible instance settings.
- [main.py](./main.py) — Application assembly and mounts.
- [mcp_permissions/](./mcp_permissions/README.md) — Group-to-capability permissions.
- [metrics/](./metrics/) — API instrumentation.
- [proxies.py](./proxies.py) — Deferred bindings.
- [settings.py](./settings.py) — REST settings.
- [system/](./system/) — Internal state, events and health.
- [telemetry/](./telemetry/README.md) — OTLP receiver.
- [telemetry_setup/](./telemetry_setup/README.md) — Authenticated discovery of the instance-configured public logs endpoint.
- [telemetry_analytics/](./telemetry_analytics/README.md) — Administrator-only aggregate log counts.
- [personal_usage/](./personal_usage/README.md) — Authenticated owner-only daily MCP usage summaries from application persistence.
- [personal_access_tokens/](./personal_access_tokens/README.md) — General token issuance with explicit resource permissions and owner-scoped lifecycle management.
- [user_catalogue/](./user_catalogue/README.md) — Cross-kind user catalogue.
- [users/](./users/) — Unified authenticated profile, UI capabilities and profile enrichment.

# Related links

- [Hosting boundary](../hosting/README.md) — Supported composition API.
