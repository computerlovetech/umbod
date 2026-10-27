---
type: Software Module
title: "Downstream MCP discovery runtime"
description: "Application-owned downstream discovery snapshots and explicit reconciliation contracts."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [catalog.py](./catalog.py) — In-memory discovery projection.
- [definitions.py](./definitions.py) — Personal namespace definition projection.
- [loader.py](./loader.py) — Background snapshot loading.
- [models.py](./models.py) — Discovery snapshots and errors.
- [ports.py](./ports.py) — Loader and runtime contracts.

# Context not available from the code

- [ADR-008](../../../../../../../project/architecture-records/ADR-008-event-synchronized-tool-runtime.md) — Required event-synchronized discovery architecture; projections are not invocation authority and cross-worker updates are not instantaneous.
