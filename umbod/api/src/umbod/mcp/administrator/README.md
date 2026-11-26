---
type: Software Module
title: Administrator MCP boundary
description: Shared administrator tool composition and the dedicated administrator HTTP application.
---

# Files

- [__init__.py](./__init__.py) — Administrator tool registration exports.
- [application.py](./application.py) — Administrator-only MCP and HTTP factories with caller-owned persistence and telemetry.
- [composition.py](./composition.py) — Shared persistent administrator configuration assembly for both hosting modes.
- [authorization.py](./authorization.py) — Membership-based tool visibility and invocation authorization.
- [Connector configuration](./connector_configuration/README.md) — Connector configuration tools, registration, catalog adapter, and rejection mapping.
- [principal.py](./principal.py) — Authenticated administrator principal capture.
- [operation_facade.py](./operation_facade.py) — Discovery, inspection and change dispatch to core administrator operations.
- [operation_inputs.py](./operation_inputs.py) — Typed administrator operation requests.
- [operation_results.py](./operation_results.py) — Operation-tagged MCP result payloads.
- [operation_registration.py](./operation_registration.py) — Observed registration, authorization and agent-visible operation guidance.

# Related decisions

- [ADR-015: Self-describing built-in MCP tool contracts](../../../../../project/architecture-records/ADR-015-self-describing-built-in-mcp-tool-contracts.md) — Administrator tool input schemas and agent-visible descriptions.
