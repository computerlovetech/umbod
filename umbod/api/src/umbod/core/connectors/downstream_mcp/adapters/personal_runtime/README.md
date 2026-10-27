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
- [operation.py](./operation.py) — Operation protocol guard without implicit tool or remote schema lookups.
- [redaction.py](./redaction.py) — Token-reflection rejection.
- [transport.py](./transport.py) — FastMCP integration.
- [wire_models.py](./wire_models.py) — Strict protocol results.
- [wire_parsing.py](./wire_parsing.py) — Bounded JSON and SSE parsing with wire-level protocol enforcement.
