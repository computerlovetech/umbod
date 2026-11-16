---
type: Software Module
title: Personal OAuth setup validation
description: Nonsecret administrator setup discovery, validation leases and publication proof contracts.
---

# Files

- [__init__.py](./__init__.py) — Public setup service and provider contracts.
- [models.py](./models.py) — Provider discovery, validation and scope candidates without authorization artifacts.
- [ports.py](./ports.py) — Injected setup provider and receipt persistence boundaries.
- [state.py](./state.py) — Revision-bound setup states, leases and completion commands.
- [service.py](./service.py) — Explicit bounded discovery and validation with safe diagnostic observation.

# Related links

- [Receipt persistence](../stores/personal_oauth_setup.py) — Durable binding checks and compare-and-swap completion.
