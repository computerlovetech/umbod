---
type: Software Module
title: Agent token administration
description: Administrator-only REST management of public MCP agent credentials.
---

# Files

- [__init__.py](./__init__.py) — Administrator router export.
- [dependencies.py](./dependencies.py) — Verified administrator claims and request-scoped token management.
- [models.py](./models.py) — Metadata, expiry input, and one-time secret responses.
- [route_policy.py](./route_policy.py) — Administrator boundary, no-store responses, and sanitized errors.
- [routes.py](./routes.py) — Issue, list, rotate, and revoke operations.
