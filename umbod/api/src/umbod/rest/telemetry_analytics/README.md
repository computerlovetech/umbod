---
type: Software Module
title: "Telemetry analytics delivery"
description: "Administrator-only aggregate log reads through the independent analytics runtime."
---

# Files

- [__init__.py](./__init__.py) — Router export.
- [models.py](./models.py) — Validated count requests with server-owned instance scope.
- [routes.py](./routes.py) — Aggregate delivery with safe availability and group-limit failures.

# Related links

- [Analytics contracts](../../core/telemetry/analytics/README.md) — Backend-neutral query dimensions, grouping, filters and UTC buckets.
- [Reader composition](../telemetry/composition.py) — Request-created readers over the shared root-owned analytics runtime.
- [Application assembly](../main.py) — Administrator authorization, mounted dependency wiring and runtime lifetime.
- [Telemetry ingestion](../../../../../docs/reference/telemetry-ingestion.md) — Collection prerequisites and aggregate query semantics.
