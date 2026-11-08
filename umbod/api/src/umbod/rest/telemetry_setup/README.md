---
type: Software Module
title: "Telemetry setup discovery"
description: "Authenticated discovery of the configured public collector logs endpoint."
---

# Files

- [__init__.py](./__init__.py) — Router export.
- [models.py](./models.py) — Available and unavailable setup response contracts.
- [deps.py](./deps.py) — Request-scoped owner eligibility and configuration-only endpoint discovery.
- [routes.py](./routes.py) — Authenticated telemetry setup read route.

# Related documentation

- [Telemetry ingestion](../../../../../docs/reference/telemetry-ingestion.md) — Collector configuration and setup discovery contract.
- [Personal access tokens](../personal_access_tokens/README.md) — Shared owner eligibility and generic token management.
