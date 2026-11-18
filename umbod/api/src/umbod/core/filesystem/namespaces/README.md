---
type: Software Module
title: Filesystem namespaces
description: Personal and shared namespace contracts and caller or administrator workflows.
---

# Files

- [__init__.py](./__init__.py) — Public namespace contracts and services.
- [errors.py](./errors.py) — Namespace validation and deletion failures.
- [models.py](./models.py) — Namespace authority, canonical root descriptions, and shared namespace management commands.
- [ports.py](./ports.py) — Registry persistence and namespace management boundaries.
- [service.py](./service.py) — Caller discovery and issuer-bound management using coherent policy and root metadata projections.

# Related links

- [Namespace store](../stores/namespaces.py) — Serialized shared-database registry, empty namespace deletion, and home adoption.
