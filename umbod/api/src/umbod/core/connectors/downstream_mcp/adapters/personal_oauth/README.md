---
type: Software Module
title: "Personal OAuth provider"
description: "Resumable authorization and refresh integration for personal downstream MCP connections."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [callback.py](./callback.py) — Issuer-bound callback policy for externally registered provider clients.
- [factory.py](./factory.py) — Provider composition.
- [network.py](./network.py) — Bounded public HTTP transport.
- [provider.py](./provider.py) — Discovery and authorization exchange.
- [refresh_logging.py](./refresh_logging.py) — Refresh diagnostic redaction.
- [refresh.py](./refresh.py) — Refresh exchange.
- [transport.py](./transport.py) — HTTP contracts and in-memory adapter.
- [validation.py](./validation.py) — Wire and provider-context validation.
