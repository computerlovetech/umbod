---
type: Software Module
title: "MCP listeners"
description: "Application-scoped adapters from neutral MCP signals to logging, metrics and audit."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [failure.py](./failure.py) — Safe receiver failure reporting.
- [invocation_audit.py](./invocation_audit.py) — Completion audit adapter.
- [invocation_logging.py](./invocation_logging.py) — Completion logging adapter.
- [invocation_metrics.py](./invocation_metrics.py) — Completion and inventory metrics.
- [registration.py](./registration.py) — Central listener composition.
