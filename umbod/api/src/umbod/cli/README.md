---
type: Software Module
title: "Command-line interface"
description: "Service startup, configuration inspection, connector validation and offline migration commands."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [api.py](./api.py) — REST service commands.
- [cleanup.py](./cleanup.py) — Explicit one-shot retention jobs and shared persistence lifetime.
- [config.py](./config.py) — Configuration inspection commands.
- [connectors.py](./connectors.py) — Structural connector validation with Python/SDK environment identification and explicit verification limits.
- [main.py](./main.py) — Command registration.
- [mcp.py](./mcp.py) — MCP startup, effective listener-port validation and supervised hosting delegation.
- [migrate.py](./migrate.py) — Offline, verified local-to-S3 file-content migration.
- [telemetry.py](./telemetry.py) — Standalone Uvicorn telemetry receiver command.

# Related knowledge

- [Hosting boundary](../hosting/README.md) — Supported service composition.
- [ADR-003](../../../../project/architecture-records/ADR-003-umbod-specific-connector-cli.md) — Umbod-specific CLI ownership versus SDK authoring tools.
