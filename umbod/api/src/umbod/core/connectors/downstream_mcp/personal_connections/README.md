---
type: Software Module
title: "Personal connections"
description: "Owner-scoped connection lifecycle, identity, authorization and refresh contracts."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [authorization_models.py](./authorization_models.py) — Saved OAuth grants.
- [caller.py](./caller.py) — Current-operation personal callers.
- [development_identity_models.py](./development_identity_models.py) — Simulated identity data.
- [development_identity.py](./development_identity.py) — Local identity eligibility.
- [grant_binding.py](./grant_binding.py) — Saved-grant policy validation.
- [health_models.py](./health_models.py) — Authorization health observations.
- [health_ports.py](./health_ports.py) — Health read contracts.
- [identity_models.py](./identity_models.py) — Personal identity facts and policy.
- [identity_ports.py](./identity_ports.py) — Identity resolver contract.
- [inmemory.py](./inmemory.py) — In-memory lifecycle store.
- [inventory_models.py](./inventory_models.py) — Selection queries and projections.
- [inventory_ports.py](./inventory_ports.py) — Selection contracts.
- [inventory.py](./inventory.py) — User selection operations.
- [models.py](./models.py) — Ownership keys and lifecycle state.
- [oauth_callback_models.py](./oauth_callback_models.py) — Callback route bindings.
- [oauth_models.py](./oauth_models.py) — Durable authorization attempts.
- [oauth_ports.py](./oauth_ports.py) — Attempt and provider contracts.
- [oauth_service.py](./oauth_service.py) — Authorization orchestration.
- [ports.py](./ports.py) — Connection storage contracts.
- [principal.py](./principal.py) — Canonical identity resolution.
- [refresh_models.py](./refresh_models.py) — Refresh reservation state.
- [refresh_ports.py](./refresh_ports.py) — Refresh storage contracts.
- [refresh_provider_models.py](./refresh_provider_models.py) — Refresh provider outcomes.
- [refresh_provider_ports.py](./refresh_provider_ports.py) — Refresh provider contract.
- [refresh_service.py](./refresh_service.py) — Refresh orchestration.
- [runtime_models.py](./runtime_models.py) — Internal admission targets.
- [runtime_ports.py](./runtime_ports.py) — Personal runtime transport contracts.
- [service.py](./service.py) — Connection lifecycle operations.
