---
type: Software Module
title: "Personal OAuth provider"
description: "Resumable authorization and refresh integration for personal downstream MCP connections."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [callback.py](./callback.py) — Trusted callback policy.
- [factory.py](./factory.py) — Provider composition.
- [network.py](./network.py) — Bounded public HTTP transport.
- [provider.py](./provider.py) — Discovery and authorization exchange.
- [refresh_logging.py](./refresh_logging.py) — Refresh diagnostic redaction.
- [refresh.py](./refresh.py) — Refresh exchange.
- [transport.py](./transport.py) — HTTP contracts and in-memory adapter.
- [validation.py](./validation.py) — Wire and provider-context validation.

# Context

Preconfigured provider clients must externally register issuer-bound callback URIs when issuer response support is absent; administrator policy is not rewritten during authorization.
