---
type: Software Module
title: "Trusted root provisioning"
description: "Explicit one-time root bootstrap for trusted filesystem configuration."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [models.py](./models.py) — Bootstrap specifications.
- [ports.py](./ports.py) — Provisioning contract.
- [service.py](./service.py) — Root bootstrap transaction.

# Context

Bootstrap is not reconciliation: configuration changes do not update an already provisioned root. Use [root policy administration](../administration/README.md) for ongoing group access editing.
