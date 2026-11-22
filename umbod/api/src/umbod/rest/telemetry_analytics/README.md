---
type: Software Module
title: "Telemetry analytics delivery"
description: "Administrator and personal aggregate log reads through the independent analytics runtime."
---

# Files

- [__init__.py](./__init__.py) — Separate administrator and personal router exports.
- [models.py](./models.py) — Validated count requests that cannot select scope.
- [routes.py](./routes.py) — Server-scoped instance and caller counts with safe availability failures.

# Related links

- [Analytics contracts](../../core/telemetry/analytics/README.md) — Backend-neutral query dimensions, grouping, filters and UTC buckets.
- [Reader composition](../telemetry/composition.py) — Request-created readers over the shared root-owned analytics runtime.
- [Application assembly](../main.py) — Administrator and signed-in authorization, mounted dependency wiring and runtime lifetime.
