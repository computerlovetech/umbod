---
type: Software Module
title: "Official MCP Registry adapter"
description: "Searches the official registry and returns compatible hosted MCP endpoints without contacting them."
---

# Files

- [__init__.py](./__init__.py) — Public adapter and composition exports.
- [official.py](./official.py) — Read-only registry lookup, compatible endpoint filtering, and HTTP client lifetime.
- [schemas.py](./schemas.py) — Validated subset of the registry response.
- [Core registry contracts](../../core/mcp_registry/README.md) — Provider-independent search port and result types.
