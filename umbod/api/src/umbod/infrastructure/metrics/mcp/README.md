---
type: Software Module
title: MCP metrics infrastructure
description: Prometheus recording and HTTP scrape serving for MCP observations.
---

# Files

- [__init__.py](./__init__.py) — Public recorder, scrape listener and composition exports.
- [composition.py](./composition.py) — Isolated recorder and bound listener factory implementing MCP contracts.
- [prometheus.py](./prometheus.py) — Prometheus registry, collectors, label mapping, histograms, and exposition.
- [http_server.py](./http_server.py) — Scrape endpoint and listener startup, shutdown, and process signal isolation.

# Related modules

- [MCP metrics](../../../mcp/metrics/README.md) — Backend-neutral measurement contracts.
- [MCP telemetry](../../../mcp/telemetry/README.md) — Application-owned dependency and listener lifecycle ports.
