---
type: Software Module
title: Observed identity directory
description: Minimal observed identities and membership values independent of authorization.
---

# Files

- [models.py](./models.py) — Immutable observations, directory results and profile merging.
- [ports.py](./ports.py) — Directory observation and search contract.
- [schema.py](./schema.py) — Backend-neutral user and membership-value tables.
- [store.py](./store.py) — Serialized observation persistence and scoped literal searches.
- [service.py](./service.py) — Best-effort observation with sanitized failure logging.

# Related links

- [ADR-012](../../../../../project/architecture-records/ADR-012-login-observed-identity-directory.md) — Directory trust and storage boundaries.
