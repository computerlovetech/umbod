---
type: Software Module
title: "Filesystem discovery"
description: "Caller-specific discovery authorization and synchronized runtime state."
---

# Files

- [__init__.py](./__init__.py) — Public discovery runtime and visibility exports.
- [authorization.py](./authorization.py) — Caller-specific tool and resource-template visibility with independent endpoint-scope restrictions.
- [runtime.py](./runtime.py) — Caller-neutral authorization snapshots hydrated at startup and reconciled through durable events.
