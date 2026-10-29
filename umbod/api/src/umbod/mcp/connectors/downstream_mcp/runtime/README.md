---
type: Software Module
title: "Downstream MCP discovery runtime"
description: "Application-owned downstream discovery snapshots and explicit reconciliation contracts."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [catalog.py](./catalog.py) — In-memory discovery projection.
- [Personal discovery](../personal_discovery.py) — Owner-specific operation snapshots composed with the shared runtime.
- [loader.py](./loader.py) — Background snapshot loading.
- [models.py](./models.py) — Discovery snapshots and errors.
- [ports.py](./ports.py) — Loader and runtime contracts.

# Architecture

- [ADR-008](../../../../../../../project/architecture-records/ADR-008-event-synchronized-tool-runtime.md) — Required event-synchronized discovery architecture; projections are not invocation authority and cross-worker updates are not instantaneous.
