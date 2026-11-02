---
type: Software Module
title: "Telemetry receiver"
description: "OTLP HTTP JSON ingestion for logs, metrics and traces."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [body.py](./body.py) — Bounded gzip and uncompressed reads.
- [composition.py](./composition.py) — Receiver route composition.
- [dependencies.py](./dependencies.py) — Bearer authentication, sinks and analytics reader/writer providers.
- [errors.py](./errors.py) — Safe receiver failures.
- [routes.py](./routes.py) — Ingestion coordination.
- [validation.py](./validation.py) — OTLP JSON validation and canonical protobuf parsing.
- [normalization.py](./normalization.py) — OTLP log projection into ownerless analytical records.

# Related links

- [Telemetry ingestion](../../../../../docs/reference/telemetry-ingestion.md) — Operator and deployment contract.
