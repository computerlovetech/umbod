---
type: Software Module
title: "Personal MCP transport"
description: "Owner-bound MCP transport with bounded protocol and network integration."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [factory.py](./factory.py) — Production transport composition.
- [http.py](./http.py) — HTTP client and pool bridge.
- [inmemory.py](./inmemory.py) — Scripted transport adapter.
- [network.py](./network.py) — Public-address and TLS enforcement.
- [operation.py](./operation.py) — Operation protocol guard.
- [redaction.py](./redaction.py) — Token-reflection rejection.
- [transport.py](./transport.py) — FastMCP integration.
- [wire_models.py](./wire_models.py) — Strict protocol results.
- [wire_parsing.py](./wire_parsing.py) — Bounded JSON and SSE parsing.

# Context

The SDK's higher-level tool-call helper is deliberately avoided because it performs implicit tool lookups and may retrieve remote schema references. The SDK has no public SSE reconnection-disable switch, so protocol enforcement remains at the wire boundary.

The reviewed dependency boundary is FastMCP 4.0.10, MCP 2.0.0, httpx2 2.10.0 and httpcore2 2.10.0.
