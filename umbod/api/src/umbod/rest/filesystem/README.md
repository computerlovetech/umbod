---
type: Software Module
title: "Filesystem REST"
description: "Authenticated user filesystem browsing and empty node creation with a separate planned-contract boundary."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [deps.py](./deps.py) — Request-local caller and service composition.
- [errors.py](./errors.py) — Safe domain error translation.
- [models.py](./models.py) — Creation inputs and child envelopes.
- [planned/](./planned/README.md) — Unavailable design-only operations.
- [routes.py](./routes.py) — Browsing and empty creation routes.

# Context not available from the code

- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem storage and ownership boundary.
- [Planned contracts](planned/README.md) — Only browsing and empty JSON file/directory creation are implemented here; multipart upload, content, rename/move, deletion and sharing remain unavailable.
