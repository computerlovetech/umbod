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
