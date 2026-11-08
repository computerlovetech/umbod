---
type: Software Module
title: Caller filesystem homes
description: Stable caller-owned upload destinations without ancestor grants.
---

# Files

- [__init__.py](./__init__.py) — Public contracts and service exports.

- [models.py](./models.py) — Exact issuer/user bindings to stable node identities.
- [ports.py](./ports.py) — Atomic home binding, namespace and ownership transaction contracts.
- [service.py](./service.py) — Idempotent private-home provisioning through an injected identity resolver, with fail-closed binding and root ownership checks.
