---
type: Software Module
title: SQLite telemetry analytics
description: File-backed analytics storage independent of application persistence.
---

# Files

- [Database](database.py) — Path isolation, readiness, connections, and shutdown coordination.
- [Schema](schema.py) — Database identity, transactional schema upgrades, and unavailable historical normalization evidence.
- [Reader](reader.py) — Parameterized SQL counts, grouping, filtering, and time buckets.
- [Writer](writer.py) — Atomic append-only analytics dimensions and versioned normalized records.
- [Values](values.py) — Exact UTC microsecond conversions.
