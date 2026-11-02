---
type: Software Module
title: SQLite telemetry analytics
description: File-backed analytics storage independent of application persistence.
---

# Files

- [Database](database.py) — Path isolation, readiness, connections, and shutdown coordination.
- [Schema](schema.py) — Analytics database identity and schema preparation.
- [Reader](reader.py) — Parameterized SQL counts, grouping, filtering, and time buckets.
- [Writer](writer.py) — Atomic append-only log batches.
- [Values](values.py) — Exact UTC microsecond conversions.
