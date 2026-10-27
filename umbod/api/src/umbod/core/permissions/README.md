---
type: Software Module
title: Permissions
description: Group permission contracts, assignable target policies and persisted grants.
---

# Files

- [__init__.py](./__init__.py)
- [catalog.py](./catalog.py) — Assignable target composition.
- [domain.py](./domain.py)
- [factories.py](./factories.py)
- [management.py](./management.py)
- [notifier.py](./notifier.py)
- [ports.py](./ports.py)
- [read_state.py](./read_state.py) — Deferred assignable publication and activation reads.
- [runtime.py](./runtime.py)
- [stores](./stores/) — Grant persistence and scoped query builders.

# Context not available from the code

- [ADR-009](../../../../../project/architecture-records/ADR-009-deferred-read-planning.md) — Planned projections are not mutation or invocation authority.
