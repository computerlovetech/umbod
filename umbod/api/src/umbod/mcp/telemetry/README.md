---
type: Software Module
title: MCP telemetry composition
description: Required application telemetry dependencies and configured listener composition.
---

# Files

- [__init__.py](./__init__.py) — Public telemetry contracts.
- [ports.py](./ports.py) — Composite metrics recording and listener lifecycle ports.
- [dependencies.py](./dependencies.py) — Required application-owned telemetry and failure-publishing dependencies.
- [composition.py](./composition.py) — Fresh failure channels, recording adapters, and listener composition.

# Related modules

- [Metrics](../metrics/README.md) — Invocation and protocol metric adapters.
- [Logging](../logging/) — Invocation and audit recording.
- [Application composition](../public_app.py) — Injected telemetry consumption and listener lifetime.
