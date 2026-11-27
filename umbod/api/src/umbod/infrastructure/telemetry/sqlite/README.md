---
type: Software Module
title: SQLite telemetry analytics
description: File-backed analytics storage independent of application persistence.
---

# Files

- [Database](database.py) — Path isolation, readiness, connections, and shutdown coordination.
- [Schema](schema.py) — Database identity, transactional schema upgrades, and unavailable historical normalization evidence.
- [Reader](reader.py) — Parameterized SQL counts, grouping, filtering, and time buckets.
- [Harness activity reader](activity_reader.py) — Owner-scoped ranked tools, searchable session pages, and session details.
- [Writer](writer.py) — Atomic append-only analytics dimensions and versioned normalized records.
- [Backfill](backfill.py) — Existing-schema connections and metadata-only selection.
- [Replay](replay.py) — Reads eligible archives and replaces only the selected batch’s unified rows atomically.
- [Values](values.py) — Exact UTC microsecond conversions.
