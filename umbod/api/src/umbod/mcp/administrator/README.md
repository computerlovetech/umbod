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
- [catalog.py](./catalog.py) — Existing connector catalogs used by configuration operations.
- [connector_configuration.py](./connector_configuration.py) — Observed built-in administrator tool registration.
- [errors.py](./errors.py) — Safe configuration rejection mapping.
- [principal.py](./principal.py) — Authenticated administrator principal capture.
- [tools.py](./tools.py) — Configuration read and mutation adapters with operation progress.
