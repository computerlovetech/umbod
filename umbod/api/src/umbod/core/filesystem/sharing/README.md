---
type: Software Module
title: "Node group sharing"
description: "Caller-authorized direct-node sharing summaries, additive group grants and policy replacement."
---

# Files

- [__init__.py](./__init__.py) — Public sharing contracts and errors.
- [errors.py](./errors.py) — Invalid recipients, protected collisions and unavailable issuer configuration.
- [models.py](./models.py) — Frozen group recipients, additive results, discriminated batch summaries, replacement commands and policy views.
- [ports.py](./ports.py) — Sharing operations and session-bound recipient and grant collaborators.
- [service.py](./service.py) — Direct authority, additive permission unions, no-write repeats, batch summaries, canonical revisions and protected replacement.

# Related links

- [Group policy rules](../group_policy.py) — Shared root and node group validation and grant canonicalization.
- [Sharing persistence](../stores/sharing.py) — Collaborators composed from one serialized database session.
- [Sharing tests](../../../../../tests/umbod/core/filesystem/sharing/) — Public behavior across ports, persistence drivers and concurrent writers.
- [ADR-013](../../../../../../project/architecture-records/ADR-013-direct-node-group-sharing.md) — Approved sharing boundaries and concurrency contract.
