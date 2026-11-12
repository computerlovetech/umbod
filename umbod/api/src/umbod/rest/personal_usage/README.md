---
type: Software Module
title: Personal usage API
description: Authenticated owner-only usage summaries from application persistence with bounded UTC windows.
---

# Files

- [__init__.py](./__init__.py) — Personal usage router export.
- [deps.py](./deps.py) — Trusted owner capture, request-scoped storage reader, availability checks, and injectable query clock.
- [models.py](./models.py) — Strict personal query and response contracts with separate ownership and UI identity fencing.
- [routes.py](./routes.py) — Normal-user usage endpoint with zero-filled counts and explicit storage failure handling.

# Related modules

- [Usage domain](../../core/usage/README.md) — Immutable records, OTEL projection, replay-safe rollups, and owner-scoped reads.
- [Feature specification](../../../../../project/specifications/personal-usage-analytics.md) — Collection, isolation, eventual consistency, and Dashboard acceptance criteria.
