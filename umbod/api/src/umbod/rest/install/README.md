---
type: Software Module
title: Public harness installation
description: Read-only scripts and packages bound to configured public API and MCP endpoints with wheel-bundled canonical resources.
---

# Files

- [__init__.py](./__init__.py) — Installation router export.
- [routes.py](./routes.py) — Finite GET/HEAD package downloads and inline instance-bound installers with no-store and nosniff.
- [deps.py](./deps.py) — Per-request resource and service providers with sanitized configuration and installer failure responses.
- [resources.py](./resources.py) — Bounded distribution resource reads for canonical package resources and installer sources.
- [install.sh](./assets/install.sh) — Verifies Bash plugin installs and optionally configures Claude Code logs-only telemetry from a private installer payload.
- [install.ps1](./assets/install.ps1) — Verifies Windows PowerShell plugin installs and optionally configures Claude Code logs-only telemetry from a private installer payload.
