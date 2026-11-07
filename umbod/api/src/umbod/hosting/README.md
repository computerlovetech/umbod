---
type: Software Module
title: "Backend hosting"
description: "Supported composition boundary for REST, MCP, telemetry services and explicit ASGI embedding."
---

# Files

- [__init__.py](./__init__.py) — Deferred package exports preserving original owner identities.
- [api_server.py](./api_server.py) — Single-process REST and private collector hosting with shared analytics and development reload.
- [applications.py](./applications.py) — Application composition.
- [contracts.py](./contracts.py) — Supported hosting contracts.
- [listeners.py](./listeners.py) — Supervised HTTP listeners, parent-owned ASGI lifespans, readiness and shutdown.
- [mcp_service.py](./mcp_service.py) — MCP service entrypoint.
- [rest_service.py](./rest_service.py) — REST service entrypoint.
- [shutdown.py](./shutdown.py) — Lightweight process shutdown deadline independent of application composition.
- [telemetry_service.py](./telemetry_service.py) — Independent telemetry service entrypoint without REST startup dependencies.

# Related links

- [ADR-004](../../../../project/architecture-records/ADR-004-single-backend-api-and-desktop-boundary.md) — Backend-owned composition and host boundary; the retired Desktop product is not a supported host.
- [Service topology](../../../../docs/operations/service-topology.md) — API and private collector listeners, MCP deployment and storage boundaries.
- [Personal authorization specification](../../../../docs/operations/personal-downstream-mcp-authorization-specification.md) — Gateway callback exemptions and credential ownership requirements.
