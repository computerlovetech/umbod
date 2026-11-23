---
type: Software Module
title: Public harness installation
description: Public packages and installer scripts bound to the instance's API, MCP and optional telemetry endpoints.
---

# Files

- [__init__.py](./__init__.py) — Installation router export.
- [routes.py](./routes.py) — Finite GET/HEAD package downloads and inline instance-bound installers with no-store and nosniff.
- [deps.py](./deps.py) — Per-request resource and service providers with sanitized configuration and installer failure responses.
- [resources.py](./resources.py) — Bounded distribution resource reads for canonical package resources and installer sources.
- [install.sh](./assets/install.sh) — Verifies Bash plugin installs and redeems optional telemetry setup claims.
- [install.ps1](./assets/install.ps1) — Verifies PowerShell plugin installs and redeems optional telemetry setup claims.
