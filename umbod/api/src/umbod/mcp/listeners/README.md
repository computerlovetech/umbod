---
type: Software Module
title: "MCP listeners"
description: "Application-scoped adapters from neutral MCP signals to logging, metrics and audit."
---

# Files

- [capability_logging.py](./capability_logging.py) — Resource and prompt completion formatting and structured logging receiver.
- [__init__.py](./__init__.py) — Package exports.
- [invocation_audit.py](./invocation_audit.py) — Completion audit adapter.
- [invocation_logging.py](./invocation_logging.py) — Completion logging adapter.
- [invocation_metrics.py](./invocation_metrics.py) — Completion and inventory metrics.
- [registration.py](./registration.py) — Listener composition and publication of receiver failures to the diagnostic channel.

# Related modules

- [Shared logging](../../logging.py) — Safe application-failure receivers and terminal dispatch-failure logging.
