---
type: Software Module
title: "Shared connector OAuth"
description: "Host-owned shared authorization coordination and injected session boundaries."
---

# Files

- [__init__.py](./__init__.py) — Package boundary.
- [ports.py](./ports.py) — Host, authorization-session and validated metadata discovery contracts.
- [service.py](./service.py) — Shared sign-in, callback, refresh and diagnostics coordination.
- [provider.py](./provider.py) — Public-client authorization policy and safe failure categories.
- [discovery.py](./discovery.py) — Public metadata discovery with URL, issuer and response-size validation.

# Integration

- [oauth_composition.py](../adapters/oauth_composition.py) — Explicit production service assembly; the caller retains service lifecycle ownership.
- [oauth_session.py](../adapters/fastmcp/oauth_session.py) — Fresh FastMCP authorization sessions for each sign-in or refresh.
- [oauth_discovery.py](../adapters/oauth_discovery.py) — Operation-owned injected HTTP discovery contexts.
