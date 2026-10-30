---
type: Software Module
title: "Group catalogue"
description: "Shared catalogue of exact group values and usage-checked registration lifecycle."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [models.py](./models.py) — Exact identifiers, metadata, revision conflicts, and registration commands.
- [ports.py](./ports.py) — Catalogue and usage contracts.
- [service.py](./service.py) — Idempotent registration, revision-checked metadata updates, and usage-checked deletion without access grants.
- [stores/](./stores/) — Catalogue persistence and usage composition.
