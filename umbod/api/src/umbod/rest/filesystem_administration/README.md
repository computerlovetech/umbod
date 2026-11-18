---
type: Software Module
title: "Filesystem namespace administration"
description: "Authenticated shared namespace management."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [deps.py](./deps.py) — Request-local management composition with the configured backend issuer.
- [routes.py](./routes.py) — No-store shared namespace listing, creation, revision-checked replacement, and empty namespace deletion.

# Architecture

- [ADR-006](../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem storage boundary and scoped policy administration detail.
