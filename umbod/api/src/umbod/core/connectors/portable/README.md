---
type: Software Module
title: Portable connector core
description: Author-owned portable drafts and internal execution of known sources with per-invocation HTTP grants.
---

# Files

- [drafts/](./drafts/README.md) — Save and read immutable author-owned source revisions without executing them.
- [draft_validation/](./draft_validation/README.md) — Inspect a saved revision separately and return author-facing compatibility diagnostics.
- [runtime.py](./runtime.py) — Offline preparation and invocation with an injected transport; no live egress or catalog publication.
- [contracts.py](./contracts.py) — Prepared connector snapshot, host grants, and execution limits.
- [ports.py](./ports.py) — Isolated sandbox session and HTTP callback contracts.
- [validation.py](./validation.py) — Manifest and invocation validation with no network schema retrieval.
- [Monty adapter](../../../infrastructure/portable_connectors/README.md) — Fresh interpreter sessions for known, host-selected sources.
