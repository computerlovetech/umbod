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
- [dependencies.py](./dependencies.py) — Shared-bearer and scoped personal-token authentication, sinks and analytics providers.
- [token_authentication.py](./token_authentication.py) — Authoritative PAT verification and owner identity, with explicit local-token eligibility.
- [errors.py](./errors.py) — Safe receiver failures.
- [observations.py](./observations.py) — Immutable collector request and accepted-log facts.
- [middleware.py](./middleware.py) — Bounded ingestion request observations, excluding health checks and unknown paths.
- [metrics.py](./metrics.py) — Backend-neutral recorder contract for collector request and accepted-log observations.
- [responses.py](./responses.py) — Encoding-matched OTLP success and safe status responses.
- [routes.py](./routes.py) — Ingestion coordination.
- [validation.py](./validation.py) — OTLP JSON and binary protobuf validation with canonical payload conversion.
- [normalization.py](./normalization.py) — Allowlisted OTLP decoding into normalization evidence and analytics projections with server-authenticated ownership.
