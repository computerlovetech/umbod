---
type: Software Module
title: "Telemetry"
description: "Validated export batches, delivery sinks and backend-neutral analytical read contracts."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [adapters/](./adapters/) — In-memory and structured logging sinks.
- [analytics/](./analytics/README.md) — Scoped log-count queries, aggregate results and asynchronous reader port.
- [normalization/](./normalization/README.md) — Transport-neutral producer evidence and canonical activity interpretation.
- [models.py](./models.py) — Export batches.
- [ports.py](./ports.py) — Sink delivery contract.
