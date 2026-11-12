---
type: Software Module
title: Personal usage
description: Owner-scoped MCP completion records, canonical OTEL projection and replay-safe daily rollups.
---

# Files

- [__init__.py](./__init__.py) — Public usage record, ownership, OTEL, and persistence-port contracts.
- [models.py](./models.py) — Immutable usage records, trusted ownership, query windows, and coherent summary counts.
- [ports.py](./ports.py) — Batch persistence, retention and owner-scoped read contracts.
- [ownership.py](./ownership.py) — Trusted issuer/subject ownership resolution.
- [otel.py](./otel.py) — Allowlisted canonical OTEL Logs serialization.
- [schema.py](./schema.py) — Backend-neutral event ledger and owner/day/category/outcome rollup tables.
- [store.py](./store.py) — Fail-fast serialized deduplicated writes, indexed retention, and bounded zero-filled daily reads.

# Related documentation

- [Personal usage specification](../../../../../project/specifications/personal-usage-analytics.md) — Collection, storage and personal reporting requirements.
- [Persistence boundaries](../../../../../project/architecture-records/ADR-001-backend-neutral-persistence.md) — Application runtime ownership and backend-neutral storage boundaries.
