---
type: Software Module
title: "MCP middleware"
description: "Protocol audit and metrics adapters independent of connector execution."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [audit.py](./audit.py) — Request-level audit.
- [protocol_metrics.py](./protocol_metrics.py) — Protocol timing and list-size observations.
- [response_metadata.py](./response_metadata.py) — Release/request correlation with preserved built-in outcome metadata and conversation-visible error context.
