---
type: Software Module
title: "Command-line interface"
description: "Service startup, configuration inspection and connector validation commands."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [api.py](./api.py) — REST service commands.
- [config.py](./config.py) — Configuration inspection commands.
- [connectors.py](./connectors.py) — Connector validation commands.
- [main.py](./main.py) — Command registration.
- [mcp.py](./mcp.py) — MCP service commands.

# Context not available from the code

- [Hosting boundary](../hosting/README.md) — Supported service composition.
- [ADR-003](../../../../project/architecture-records/ADR-003-umbod-specific-connector-cli.md) — Umbod-specific CLI ownership versus SDK authoring tools.
