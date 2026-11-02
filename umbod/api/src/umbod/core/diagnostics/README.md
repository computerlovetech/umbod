---
type: Software Module
title: Application diagnostics
description: Immutable safe failure notifications published through application-local signals.
---

# Files

- [__init__.py](./__init__.py) — Public diagnostic event and publishing API.
- [models.py](./models.py) — Typed failure kinds, approved contexts, and immutable event snapshots.
- [capture.py](./capture.py) — Safe snapshots, signal publication, and publishing receiver-failure handling.

# Related modules

- [Signals](../signals/README.md) — Typed publishing ports and isolated receiver dispatch.
- [Shared logging](../../logging.py) — Configured failure channels, logging receivers, and terminal fallback.
