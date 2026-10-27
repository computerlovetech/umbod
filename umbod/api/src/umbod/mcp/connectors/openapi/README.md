---
type: Software Module
title: "OpenAPI MCP boundary"
description: "MCP discovery and execution adapters for OpenAPI-generated capabilities."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [availability.py](./availability.py) — Execution availability.
- [codemode_execution.py](./codemode_execution.py) — Code-mode execution.
- [configuration.py](./configuration.py) — Adapter configuration.
- [deps.py](./deps.py) — Caller and persistence dependencies.
- [discovery_runtime.py](./discovery_runtime.py) — Application discovery projection.
- [factories.py](./factories.py) — Adapter composition.
- [inventory.py](./inventory.py) — Inventory observations.
- [ports.py](./ports.py) — Composition contracts.

# Context not available from the code

- [ADR-008](../../../../../../project/architecture-records/ADR-008-event-synchronized-tool-runtime.md) — Required event-synchronized discovery architecture; projections are not invocation authority and cross-worker updates are not instantaneous.
