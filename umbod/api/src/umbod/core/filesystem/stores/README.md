---
type: Software Module
title: "Filesystem stores"
description: "Database-neutral namespace and access-policy persistence."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [access_control.py](./access_control.py) — Ownership, grants and complete per-node policy cleanup.
- [authorization_facts.py](./authorization_facts.py) — Bounded ACL reads scoped to validated managed descendants.
- [discovery.py](./discovery.py) — Coherent read-only authorization snapshots without root initialization or writer reservations.
- [discovery_events.py](./discovery_events.py) — Sanitized durable invalidation events appended within namespace and policy transactions.
- [exploration.py](./exploration.py) — Read-only complete ancestry and namespace-bounded ACL capture before authorized child enumeration.
- [group_usage.py](./group_usage.py) — Group catalogue usage checks.
- [homes.py](./homes.py) — Exact issuer/user home bindings and serialized namespace, ownership and binding transactions.
- [namespace.py](./namespace.py) — Node persistence, revision-checked mutations and namespace boundary protection.
- [namespaces.py](./namespaces.py) — Serialized registry, private shared-root containers, lazy legacy rename relocation, group policies and home adoption.
- [schema.py](./schema.py) — Node and access-policy tables.
- [session.py](./session.py) — Storage failure translation.
- [sharing.py](./sharing.py) — Serialized sharing sessions with registered recipient and grant collaborators.
- [transactions.py](./transactions.py) — Combined namespace and policy writes.
- [uploads.py](./uploads.py) — Upload session table and combined publication transactions.

# Related links

- [ADR-001](../../../../../../project/architecture-records/ADR-001-backend-neutral-persistence.md) — Store ownership and application-managed persistence lifetimes.
