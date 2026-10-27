---
type: Software Module
title: Connector initialization
description: Planning and applying connector scaffolding within an existing Hatch src-package project.
---

# Files

- [__init__.py](./__init__.py) — Public planning interface.
- [adapters.py](./adapters.py) — Project file operations.
- [cli.py](./cli.py) — Connector init command.
- [models.py](./models.py) — Requests and plans.
- [port.py](./port.py) — Project file contract.
- [service.py](./service.py) — Initialization planning and application.

# Context not available from the code

- [ADR-003](../../../../../umbod/project/architecture-records/ADR-003-umbod-specific-connector-cli.md) — SDK connector CLI scope.
- After an apply failure, inspect the reported paths rather than assuming automatic cleanup; writes across project files are not atomic.
