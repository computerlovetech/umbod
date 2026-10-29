---
type: Software Module
title: "Filesystem deletion"
description: "Transaction-scoped authorization and permanent single-file namespace and policy removal."
---

# Files

- [__init__.py](./__init__.py) — Public deletion service and port.
- [ports.py](./ports.py) — Eligibility and expected-revision file removal contract.
- [service.py](./service.py) — Direct-node authorization and atomic namespace/policy removal without content I/O.

# Related links

- [Filesystem transactions](../transactions.py) — Shared serialized namespace and policy boundary.
- [ADR-006](../../../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Neutral stores and independent content lifetime.
