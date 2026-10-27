---
type: Software Module
title: "MCP messaging"
description: "Durable event delivery and lifecycle synchronization of MCP runtime projections."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [projection.py](./projection.py) — Bootstrap, replay and synchronization health.
- [transport.py](./transport.py) — Database and HTTP event adapters.

# Context not available from the code

- [ADR-008](../../../../../project/architecture-records/ADR-008-event-synchronized-tool-runtime.md) — Required event-synchronized discovery architecture; projections are not invocation authority and cross-worker updates are not instantaneous.
