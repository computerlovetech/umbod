---
type: Software Module
title: "MCP metrics"
description: "Backend-neutral invocation and protocol observations and recording contracts."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [models.py](./models.py) — Invocation observation models.
- [protocol_models.py](./protocol_models.py) — Protocol observation models.
- [protocol_recorder.py](./protocol_recorder.py) — Protocol recording contract.
- [recorder.py](./recorder.py) — Invocation recording contract.

# Related modules

- [Infrastructure metrics](../../infrastructure/metrics/README.md) — Prometheus exporters and HTTP scrape listeners.
- [Invocation receiver](../listeners/invocation_metrics.py) — Tool-call observation and inventory initialization policy.
- [Protocol middleware](../middleware/protocol_metrics.py) — Protocol timing, outcomes, and returned tool counts.
