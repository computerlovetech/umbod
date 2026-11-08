---
type: Software Module
title: Personal access tokens
description: General authenticated token issuance with explicit resource permissions and owner-scoped lifecycle management.
---

# Files

- [__init__.py](./__init__.py) — Personal API router export.
- [routes.py](./routes.py) — Permission-configured issuance, all-owner token metadata listing and direct owner-qualified revocation.
- [deps.py](./deps.py) — Request-scoped token services over the existing application persistence runtime.
- [models.py](./models.py) — Explicit name, expiry and permissions input plus the one-time secret response.
- [errors.py](./errors.py) — Sanitized operation failures and fail-closed trusted-identity handling.

# Related links

- [Token core](../../core/personal_access_tokens/README.md) — Hash-only storage, supported access grants, identity, expiry and revocation.
- [Personal token contract](../../../../../docs/reference/personal-access-tokens.md) — General management endpoints, requested permissions and authentication boundaries.
- [Telemetry receiver](../telemetry/README.md) — The first consumer of permission-restricted personal tokens.
