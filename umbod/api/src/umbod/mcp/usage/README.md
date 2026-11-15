---
type: Software Module
title: MCP usage collection
description: Trusted completion projections and bounded application-local asynchronous persistence.
---

# Files

- [__init__.py](./__init__.py) — Runtime composition and immutable aggregate statistics exports.
- [composition.py](./composition.py) — Explicit signal registration, database adapter selection, and HTTP/in-process worker lifespan.
- [identity.py](./identity.py) — Trusted provider adaptation for missing Google issuer claims using approved configured Google issuers.
- [ports.py](./ports.py) — Admission, validated settings, clocks, and retry scheduler boundaries.
- [receivers.py](./receivers.py) — Trusted, privacy-safe tool/resource/prompt projections excluding discovery and orchestration wrappers.
- [statistics.py](./statistics.py) — Bounded aggregate loss counters and rate-limited sanitized application-failure observations.
- [writer.py](./writer.py) — Bounded admission, batch retries and a shared shutdown budget; retention runs separately through the cleanup CLI.

# Contracts

- [Usage domain](../../core/usage/README.md) — Shared ownership, canonical OTEL records, persistence ports, and storage.
