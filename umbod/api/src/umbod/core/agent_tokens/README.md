---
type: Software Module
title: Agent tokens
description: Administrator-managed credentials for named agents with one Umbod group and a public MCP audience.
---

# Files

- [__init__.py](./__init__.py) — Public agent token contracts and service exports.
- [errors.py](./errors.py) — Management conflicts and opaque verification failures.
- [factory.py](./factory.py) — Independent management and verification composition over the shared database.
- [generation.py](./generation.py) — Secure token entropy and the UTC system clock.
- [models.py](./models.py) — Agent identity, credential metadata, and issuance results.
- [ports.py](./ports.py) — Dependencies for group lookup, time, and credential storage.
- [service.py](./service.py) — Administrator lifecycle operations and public MCP verification against the original group instance.
- [schema.py](./schema.py) — Backend-neutral persistence schema for agent credentials and their group bindings.
- [store.py](./store.py) — Credential writes with atomic group-instance and lifecycle checks.
