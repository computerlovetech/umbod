---
type: Software Module
title: SQLite telemetry analytics
description: File-backed analytics storage independent of application persistence.
---

# Files

- [Database](database.py) — Path isolation, readiness, connections, and shutdown coordination.
- [Schema](schema.py) — Database identity, schema validation, and transactional v1 backfill; historical Codex tools retain unknown provenance.
- [Reader](reader.py) — Parameterized SQL counts, grouping, filtering, and time buckets.
- [Writer](writer.py) — Atomic append-only log batches.
- [Values](values.py) — Exact UTC microsecond conversions.
