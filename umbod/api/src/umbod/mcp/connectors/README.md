---
type: Software Module
title: Connector MCP delivery
description: Connector-kind discovery, invocation and runtime adapters for MCP delivery.
---

# Native tools

- [Discovery](./native/tools/discovery/README.md) — Search and manifests for native and OpenAPI capabilities.
- [Invocation](./native/tools/invocation/README.md) — Argument preparation, execution admission and public failure adaptation.
- [Runtime](./native/tools/runtime/README.md) — Tool exposure, discovery projections and lifecycle reconciliation.

# OpenAPI

- [OpenAPI adapters](./openapi/README.md) — MCP discovery and execution of generated capabilities.

# Downstream MCP

- [Discovery runtime](./downstream_mcp/runtime/README.md) — Application-owned snapshots and reconciliation contracts.
- [Personal discovery](./downstream_mcp/personal_discovery.py) — Owner-specific discovery composed with the shared runtime.
- [Personal recovery](./downstream_mcp/personal_recovery.py) — Safe connection links and authorization or inventory recovery errors.
