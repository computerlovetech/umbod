---
type: Software Module
title: "Backend hosting"
description: "Supported composition boundary for separate REST and MCP services and explicit ASGI embedding."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [applications.py](./applications.py) — Application composition.
- [contracts.py](./contracts.py) — Supported hosting contracts.
- [mcp_service.py](./mcp_service.py) — MCP service entrypoint.
- [rest_service.py](./rest_service.py) — REST service entrypoint.

# Context not available from the code

- [ADR-004](../../../../project/architecture-records/ADR-004-single-backend-api-and-desktop-boundary.md) — Backend-owned composition and host boundary; the retired Desktop product is not a supported host.
- [Service topology](../../../../docs/operations/service-topology.md) — Separate REST and MCP deployment.
- [Personal authorization specification](../../../../docs/operations/personal-downstream-mcp-authorization-specification.md) — Gateway callback exemptions and credential ownership requirements.
