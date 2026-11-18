---
type: Software Module
title: "Infrastructure"
description: "Concrete storage and metrics adapters with explicit infrastructure composition boundaries."
---

# Files

- [__init__.py](./__init__.py) — Public composition exports with deferred metrics factory loading.
- [connections/](./connections/README.md) — Infrastructure-owned connection leases, bounded pooling and driver cleanup.
- [filesystem/](./filesystem/README.md) — Filesystem composition and content storage.
- [key_value/](./key_value/README.md) — Key-value driver composition.
- [metrics/](./metrics/README.md) — Metrics exporters, vendor clients, and HTTP scrape listeners.
- [persistence/](./persistence/README.md) — Database drivers, schema readiness and explicit personal-discovery preparation.
- [telemetry/](./telemetry/README.md) — Independently configured SQLite analytics drivers and runtime composition.

# Related links

- [ADR-001](../../../../project/architecture-records/ADR-001-backend-neutral-persistence.md) — Neutral database boundary and runtime ownership.
- [ADR-006](../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem composition boundary.
- [ADR-010](../../../../project/architecture-records/ADR-010-key-value-storage-drivers.md) — Key-value drivers remain separate from cache policy; remote retention needs an explicit design.
- [Telemetry analytics](../core/telemetry/analytics/README.md) — Neutral analytical reader, normalized writer and runtime contracts.
