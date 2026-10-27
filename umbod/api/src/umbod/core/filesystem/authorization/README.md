---
type: Software Module
title: "Filesystem authorization"
description: "Direct-node permission evaluation and caller-to-principal resolution."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [errors.py](./errors.py) — Permission denial.
- [local_resolver.py](./local_resolver.py) — Opt-in local identity mapping.
- [models.py](./models.py) — Resolved identities and decisions.
- [ports.py](./ports.py) — Resolver and authorization contracts.
- [resolver.py](./resolver.py) — Verified identity mapping.
- [service.py](./service.py) — Shared policy evaluator.

# Related links

- [Browsing](../browsing/README.md) — Authorized browsing boundary, separate from trusted raw filesystem APIs.
- [Creation](../creation/README.md) — Authorized creation boundary, separate from trusted policy APIs.
