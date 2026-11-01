---
type: Software Module
title: Observed identity directory
description: Minimal observed identities and membership values independent of authorization.
---

# Files

- [models.py](./models.py) — Immutable observations, directory results and profile merging.
- [ports.py](./ports.py) — Directory observation, name search, issuer-scoped identity lookup and reverse subject-profile lookup contracts.
- [schema.py](./schema.py) — Backend-neutral user and membership-value tables.
- [store.py](./store.py) — Serialized observations and session-bound observed-user reads reused within sharing transactions.
- [service.py](./service.py) — Best-effort observation with sanitized failure logging.
- [user_models.py](./user_models.py) — Name search with neutral subject exclusions, minimal results, identity bindings and reverse subject-profile lookup models.
- [users.py](./users.py) — Verified-caller name search and stable-ID resolution without permission changes.
