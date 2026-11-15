---
type: Software Module
title: Cleanup
description: Explicit one-shot cleanup jobs with sequential execution, time bounds and sanitized failure publication.
---

# Files

- [__init__.py](./__init__.py) — Public cleanup job and runner contracts.
- [ports.py](./ports.py) — Extensible one-shot job boundary without a global registry.
- [runner.py](./runner.py) — Sequential immutable registration, bounded execution and failure continuation.

# Related modules

- [CLI composition](../../cli/cleanup.py) — Explicit retention job tuple and persistence readiness and shutdown ownership.
- [Diagnostics](../diagnostics/README.md) — Sanitized signal-owned failure reporting.
