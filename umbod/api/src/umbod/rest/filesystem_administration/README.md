---
type: Software Module
title: "Filesystem root-access administration"
description: "Authenticated administrator delivery for root-access inspection and revision-checked group policy updates."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [deps.py](./deps.py) — Request-local management composition.
- [models.py](./models.py) — Policy transport models and hints.
- [routes.py](./routes.py) — Root-access administration routes.

# Context not available from the code

- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Trusted root setup is separate from ordinary filesystem authorization; administrator membership alone grants no user filesystem access.
