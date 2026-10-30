---
type: Software Module
title: "Planned filesystem HTTP contracts"
description: "Design-only filesystem routes that expose unavailable contracts rather than implemented storage capabilities."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [deps.py](./deps.py) — Explicit unavailable-operation responses.
- [models.py](./models.py) — Planned boundary requests and errors.
- [routes.py](./routes.py) — Three unavailable operations: owned/shared listing, content replacement and rename/move.

# Related links

- [Implemented filesystem boundary](../README.md) — Browsing, creation, transfers, deletion and direct-node group sharing are implemented separately.
- [ADR-006](../../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Storage boundary; planned HTTP contracts do not claim completed content or authorization capabilities.
