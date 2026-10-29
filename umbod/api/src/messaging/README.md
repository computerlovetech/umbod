---
type: Software Module
title: "Messaging"
description: "Shared event contracts and transport abstractions for communication between Umbod processes."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [events.py](./events.py) — Event definitions.
- [in_memory.py](./in_memory.py) — Runtime-local event checkpoints.
- [models.py](./models.py) — Envelopes and cursors.
- [no_op.py](./no_op.py) — Disabled transport.
- [ports.py](./ports.py) — Publishing and subscription contracts.
- [proxies.py](./proxies.py) — Deferred transport bindings.
