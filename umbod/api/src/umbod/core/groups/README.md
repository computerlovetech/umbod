---
type: Software Module
title: "Group catalogue"
description: "Shared catalogue of exact group values and usage-checked registration lifecycle."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [in_memory.py](./in_memory.py) — In-memory transaction adapter.
- [models.py](./models.py) — Catalogue data and commands.
- [ports.py](./ports.py) — Catalogue and usage contracts.
- [service.py](./service.py) — Registration and deletion.
- [stores/](./stores/) — Catalogue persistence and usage composition.

# Context

Catalogue registration grants no connector or filesystem access and does not manage identity-provider groups.
