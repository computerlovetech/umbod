---
type: Software Module
title: "Filesystem stores"
description: "Database-neutral namespace and access-policy persistence."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [access_control.py](./access_control.py) — Ownership and grant storage.
- [administration.py](./administration.py) — Root policy transactions.
- [group_usage.py](./group_usage.py) — Group catalogue usage checks.
- [namespace.py](./namespace.py) — Namespace persistence.
- [schema.py](./schema.py) — Node and access-policy tables.
- [session.py](./session.py) — Storage failure translation.
- [transactions.py](./transactions.py) — Combined namespace and policy writes.

# Related links

- [ADR-001](../../../../../../project/architecture-records/ADR-001-backend-neutral-persistence.md) — Store ownership and application-managed persistence lifetimes.
