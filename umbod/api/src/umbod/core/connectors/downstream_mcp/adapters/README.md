---
type: Software Module
title: "Downstream MCP adapters"
description: "Integration adapters for downstream MCP discovery, identity and personal providers."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [composition.py](./composition.py) — Independent invocation-client and discovery-probe construction with shared TLS and OAuth wiring.
- [fastmcp/](./fastmcp/) — Shared FastMCP integration.
- [icon_discovery.py](./icon_discovery.py) — Probe favicon enrichment.
- [identity.py](./identity.py) — Accepted claim translation.
- [oauth_composition.py](./oauth_composition.py) — Explicit host-owned OAuth service composition.
- [oauth_discovery.py](./oauth_discovery.py) — Injected operation-scoped HTTP metadata discovery.
- [oauth_session.py](./fastmcp/oauth_session.py) — Fresh authorization provider and client contexts per attempt.
- [personal_oauth/](./personal_oauth/README.md) — Personal OAuth provider.
- [personal_runtime/](./personal_runtime/README.md) — Personal MCP transport.
- [settings.py](./settings.py) — Configuration translation.
- [tool_mapping.py](./tool_mapping.py) — SDK tool projection.
