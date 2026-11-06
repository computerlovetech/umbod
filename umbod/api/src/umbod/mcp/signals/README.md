---
type: Software Module
title: "MCP signals"
description: "Neutral invocation and inventory signals separating execution from concrete observers."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [channels.py](./channels.py) — Typed signal channels.
- [context.py](./context.py) — Request-local correlation and nested failure classification for gateway audit records.
- [diagnostics.py](./diagnostics.py) — Invocation-local failure diagnostics.
- [events.py](./events.py) — Invocation and inventory facts.
- [execution.py](./execution.py) — Execution pipeline composition and expected rejection versus backend failure classification.
- [lifecycle.py](./lifecycle.py) — Completion timing.
- [publisher.py](./publisher.py) — Lifecycle and inventory publication.
