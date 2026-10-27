---
type: Software Module
title: Connector metadata checks
description: Connector entry-point checks, SDK compatibility and published image metadata verification.
---

# Files

- [__init__.py](./__init__.py) — Public checking interface.
- [checker.py](./checker.py) — Entry-point metadata validation.
- [cli.py](./cli.py) — Connector check command.
- [compatibility.py](./compatibility.py) — SDK compatibility.
- [models.py](./models.py) — Check requests and results.
- [port.py](./port.py) — Metadata read contract.
- [readers.py](./readers.py) — In-memory and filesystem metadata.
- [registry.py](./registry.py) — OCI release metadata.
- [registry_transport.py](./registry_transport.py) — Registry HTTP transport.

# Context not available from the code

- [ADR-003](../../../../../umbod/project/architecture-records/ADR-003-umbod-specific-connector-cli.md) — SDK connector CLI scope.
