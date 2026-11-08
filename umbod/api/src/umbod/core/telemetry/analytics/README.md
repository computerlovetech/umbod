---
type: Software Module
title: Telemetry analytics
description: Backend-neutral log counting contracts and validated aggregation models.
---

# Files

- [Activity](activity.py) — Pure producer classification; includes synthetic legacy codex/tool_result compatibility, not an upstream event contract.
- [Public exports](__init__.py) — Supported analytics contract types and errors.
- [Ports](ports.py) — Backend-neutral reader, writer, and runtime boundaries.
- [Write models](write_models.py) — Validated log records, ownership, and atomic write batches.
- [Models](models.py) — Immutable paginated queries, dimensions, scopes, time buckets, and count results.
- [Errors](errors.py) — Unavailable analytics readers.
