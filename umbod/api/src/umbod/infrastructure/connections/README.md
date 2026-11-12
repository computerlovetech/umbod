---
type: Software Module
title: Managed connections
description: Backend-neutral connection ownership, bounded leases, and cancellation-safe cleanup.
---

# Files

- [ports.py](./ports.py) — Driver and managed connection provider contracts.
- [pool.py](./pool.py) — Fixed-capacity eager pool with exclusive leases and draining shutdown.
- [direct.py](./direct.py) — Operation-owned connections for callers without a shared pool lifecycle.
- [lifecycle.py](./lifecycle.py) — Cleanup completion under repeated task and AnyIO cancellation.
- [sqlite.py](./sqlite.py) — SQLite opening and pool reset, restoring primary-write busy timeouts after best-effort leases.
- [__init__.py](./__init__.py) — Public connection pool and protocol exports.
