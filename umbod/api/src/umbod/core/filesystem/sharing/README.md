---
type: Software Module
title: "Filesystem sharing"
description: "Caller-authorized group and observed-user sharing with combined browsing summaries."
---

# Files

- [__init__.py](./__init__.py) — Public sharing contracts and errors.
- [errors.py](./errors.py) — Invalid recipients, protected collisions and unavailable issuer configuration.
- [models.py](./models.py) — Typed recipients, scoped recipient search, additive commands, summaries and policy views.
- [ports.py](./ports.py) — Sharing operations and session-bound recipient and grant collaborators.
- [projection.py](./projection.py) — Shared manageable-recipient projection, protected collisions and scope-independent policy revisions.
- [service.py](./service.py) — Effective sharing authority, bounded recipient search, normalized recursive scope, additive sharing and scoped replacement.

# Related links

- [Group policy rules](../group_policy.py) — Shared root and node group validation and grant canonicalization.
- [Sharing persistence](../stores/sharing.py) — Collaborators composed from one serialized database session.
- [Sharing tests](../../../../../tests/umbod/core/filesystem/sharing/) — Public behavior across ports, persistence drivers and concurrent writers.
