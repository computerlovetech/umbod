---
type: Software Module
title: "Command-line interface"
description: "Service startup, configuration inspection, connector validation and offline migration commands."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [api.py](./api.py) — REST service commands.
- [config.py](./config.py) — Configuration inspection commands.
- [connectors.py](./connectors.py) — Connector validation commands.
- [main.py](./main.py) — Command registration.
- [mcp.py](./mcp.py) — MCP startup, effective listener-port validation and supervised hosting delegation.
- [migrate.py](./migrate.py) — Offline, verified local-to-S3 file-content migration.
- [telemetry.py](./telemetry.py) — Standalone Uvicorn telemetry receiver command.

# Related knowledge

- [Hosting boundary](../hosting/README.md) — Supported service composition.
- [S3 operations](../../../../docs/operations/s3-file-storage.md) — Storage configuration and offline migration procedure.
- [ADR-003](../../../../project/architecture-records/ADR-003-umbod-specific-connector-cli.md) — Umbod-specific CLI ownership versus SDK authoring tools.
