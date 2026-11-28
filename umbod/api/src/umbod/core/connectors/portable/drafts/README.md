---
type: Software Module
title: Portable connector drafts
description: Author-owned source drafts and immutable connector revisions.
---

# Files

- [service.py](./service.py) — Authenticated draft creation, bounded UTF-8 source, and revision reads and saves without code execution.
- [models.py](./models.py) — Author identity, revision receipt, and exact source snapshot.
- [ports.py](./ports.py) — Storage boundary for owner-scoped reads and atomic head updates.
- [store.py](./store.py) — Backend-neutral durable store with optimistic head checks in serialized transactions.
- [schema.py](./schema.py) — Draft and revision tables registered with application persistence readiness.
- [errors.py](./errors.py) — Source, access, conflict, and storage failure outcomes.
