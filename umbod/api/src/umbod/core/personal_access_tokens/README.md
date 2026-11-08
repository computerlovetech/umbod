---
type: Software Module
title: Personal access tokens
description: Transport-neutral owner-scoped bearer-token issuance, validation and revocation with hash-only persistence.
---

# Files

- [__init__.py](./__init__.py) — Public token contracts, service and factory exports.
- [models.py](./models.py) — Immutable ownership, scope policy, metadata and redacted secret contracts.
- [access.py](./access.py) — Explicit resource permissions, supported grant resolution and issuance policy.
- [ports.py](./ports.py) — Owner resolution, token storage, clock and secure-generation interfaces.
- [ownership.py](./ownership.py) — Verified-only ownership and explicitly configured local-development identity resolution.
- [service.py](./service.py) — Trusted-caller management and audience-, scope-, expiry- and revocation-aware validation.
- [factory.py](./factory.py) — Explicit database composition with secure random generation and a UTC clock.
- [schema.py](./schema.py) — Backend-neutral token table and codecs storing metadata and hashes only.
- [store.py](./store.py) — Owner-filtered database operations and serialized revocation.
- [errors.py](./errors.py) — Credential-free authentication, ownership and collision failures.

# Related links

- [Caller identities](../callers/README.md) — Authentication provenance and issuer-qualified subjects.
- [Persistence](../persistence/README.md) — Shared database and transaction contracts.
- [ADR-001](../../../../../project/architecture-records/ADR-001-backend-neutral-persistence.md) — Persistence ownership and runtime boundaries.
