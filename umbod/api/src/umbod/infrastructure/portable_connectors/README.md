---
type: Software Module
title: Portable connector sandbox adapter
description: Monty sessions for the internal offline portable connector runtime.
---

# Files

- [sandbox.py](./sandbox.py) — Bounded sessions, curated SDK bootstrap mount, and invocation with a single host callback.
- [draft_validator.py](./draft_validator.py) — Draft loading and manifest diagnostics in fresh sessions without host callbacks.
- [draft_manifest_worker.py](./draft_manifest_worker.py) — Offline schema checks of bounded JSON in a disposable process; never receives connector source.
- [draft_imports.py](./draft_imports.py) — Bounded advisory inspection of imports inside handlers.
- [Portable connector core](../../core/connectors/portable/README.md) — Manifest validation, invocation lifecycle, and HTTP grants.
