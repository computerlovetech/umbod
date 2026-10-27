---
type: Software Module
title: Permissions
description: Group permission contracts, assignable target policies and persisted grants.
---

# Files

- [__init__.py](./__init__.py) — Public permission exports.
- [catalog.py](./catalog.py) — Assignable target composition.
- [domain.py](./domain.py) — Permission targets, grants and change requests.
- [factories.py](./factories.py) — Persistent permission store composition.
- [management.py](./management.py) — Group permission registration and mutation.
- [notifier.py](./notifier.py) — No-op permission change notifications.
- [ports.py](./ports.py) — Permission storage, catalogue and notification contracts.
- [read_state.py](./read_state.py) — Deferred assignable publication and activation reads.
- [runtime.py](./runtime.py) — In-memory group grants and runtime access resolution.
- [stores](./stores/) — Grant persistence and scoped query builders.

# Related links

- [ADR-009](../../../../../project/architecture-records/ADR-009-deferred-read-planning.md) — Planned projections are not mutation or invocation authority.
