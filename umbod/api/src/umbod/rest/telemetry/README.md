---
type: Software Module
title: "Telemetry receiver"
description: "OTLP HTTP JSON and protobuf ingestion for logs, metrics and traces."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [application.py](./application.py) — Collector-only FastAPI apps with host-injected or standalone-owned analytics and health checks.
- [body.py](./body.py) — Bounded gzip and uncompressed reads.
- [composition.py](./composition.py) — Receiver route composition.
- [dependencies.py](./dependencies.py) — Bearer authentication, sinks and analytics reader/writer providers.
- [errors.py](./errors.py) — Safe receiver failures.
- [observations.py](./observations.py) — Immutable collector request and accepted-log facts.
- [middleware.py](./middleware.py) — Bounded ingestion request observations, excluding health checks and unknown paths.
- [metrics.py](./metrics.py) — Signal receivers for collector Prometheus metrics in an explicitly supplied registry.
- [responses.py](./responses.py) — Encoding-matched OTLP success and safe status responses.
- [routes.py](./routes.py) — Ingestion coordination.
- [validation.py](./validation.py) — OTLP JSON and binary protobuf validation with canonical payload conversion.
- [normalization.py](./normalization.py) — OTLP log projection into ownerless analytical records.

# Related links

- [Telemetry ingestion](../../../../../docs/reference/telemetry-ingestion.md) — Operator and deployment contract.
