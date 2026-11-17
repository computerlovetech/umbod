---
type: Software Module
title: Agent behaviour administration
description: Authorized configuration publication and self-reported diagnostic inspection.
---

# Files

- [__init__.py](./__init__.py) — Public admin router export.
- [dependencies.py](./dependencies.py) — Request-scoped service construction from the shared persistence database.
- [routes.py](./routes.py) — Configuration CAS, bounded report queries, detail, deletion and safe non-cacheable responses.

# Related

- [Core agent behaviour](../../core/agent_behaviour/README.md) — Transport-neutral domain contracts and durable storage.
- [REST boundary](../README.md) — Existing administration authentication and application composition.
