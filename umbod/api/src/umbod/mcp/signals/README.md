---
type: Software Module
title: "MCP signals"
description: "Application-scoped tool, resource, prompt, and inventory facts separating operations from observers."
---

# Files

- [capabilities.py](./capabilities.py) — Immutable resource and prompt operation completions with fingerprinted request targets.
- [__init__.py](./__init__.py) — Package exports.
- [channels.py](./channels.py) — Typed signal channels.
- [context.py](./context.py) — Request-local correlation and nested failure classification for gateway audit records.
- [diagnostics.py](./diagnostics.py) — Invocation-local failure diagnostics.
- [events.py](./events.py) — Invocation and inventory facts with captured opaque trusted usage ownership.
- [execution.py](./execution.py) — MCP execution observation, protocol rejection translation, and completion publication.
- [lifecycle.py](./lifecycle.py) — Completion timing.
- [ports.py](./ports.py) — Focused invocation lifecycle publishing contract.
- [publisher.py](./publisher.py) — Lifecycle and inventory publication.
