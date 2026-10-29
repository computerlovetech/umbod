---
type: Software Module
title: "Infrastructure"
description: "Concrete storage adapters and composition boundaries for persistence, filesystem and key-value services."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [filesystem/](./filesystem/README.md) — Filesystem composition and content storage.
- [key_value/](./key_value/README.md) — Key-value driver composition.
- [persistence/](./persistence/README.md) — Database drivers, schema readiness and explicit personal-discovery preparation.

# Context not available from the code

- [ADR-001](../../../../project/architecture-records/ADR-001-backend-neutral-persistence.md) — Neutral database boundary and runtime ownership.
- [ADR-006](../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem composition boundary.
- [ADR-010](../../../../project/architecture-records/ADR-010-key-value-storage-drivers.md) — Key-value drivers remain separate from cache policy; remote retention needs an explicit design.
