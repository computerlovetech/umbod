---
type: Software Module
title: Telemetry setup
description: Authenticated collector discovery and single-use installer claims.
---

# Files

- [__init__.py](./__init__.py) — Router export.
- [models.py](./models.py) — Available and unavailable setup response contracts.
- [deps.py](./deps.py) — Request-scoped owner eligibility and configuration-only endpoint discovery.
- [routes.py](./routes.py) — Authenticated telemetry setup read route.
- [install_claims.py](./install_claims.py) — Authenticated claim preparation and bearer-only redemption.
- [claim_redaction.py](./claim_redaction.py) — Removes query strings from claim requests before application logging.

# Related documentation

- [Personal access tokens](../personal_access_tokens/README.md) — Shared owner eligibility and generic token management.
