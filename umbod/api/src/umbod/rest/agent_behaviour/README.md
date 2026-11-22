---
type: Software Module
title: Agent behaviour REST
description: Administrator configuration and report management, plus owner-scoped diagnostic report reads.
---

# Files

- [__init__.py](./__init__.py) — Public administrator and personal router exports.
- [dependencies.py](./dependencies.py) — Request-scoped service construction from the shared persistence database.
- [routes.py](./routes.py) — Administrator configuration and report management, with safe non-cacheable response handling.
- [personal_routes.py](./personal_routes.py) — Read-only diagnostic lists and details using authenticated personal caller context.

# Related

- [Core agent behaviour](../../core/agent_behaviour/README.md) — Transport-neutral domain contracts and durable storage.
- [REST boundary](../README.md) — Authentication and application composition.
