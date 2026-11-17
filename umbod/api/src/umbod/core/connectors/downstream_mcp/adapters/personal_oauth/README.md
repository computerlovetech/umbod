---
type: Software Module
title: "Personal OAuth provider"
description: "Resumable authorization and refresh integration for personal downstream MCP connections."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [callback.py](./callback.py) — Issuer-bound callback policy for externally registered provider clients.
- [discovery.py](./discovery.py) — Shared exact-resource and issuer validation with prioritized OAuth and OpenID not-found fallback.
- [failure.py](./failure.py) — Provider stage attribution and safe transport failure translation.
- [factory.py](./factory.py) — Provider composition.
- [metadata.py](./metadata.py) — Read-only creation discovery, explicit issuer choice and automatic-registration capability projection.
- [network.py](./network.py) — Bounded public HTTP transport.
- [provider.py](./provider.py) — Discovery, reusable confidential registration and bound authorization exchange.
- [refresh_logging.py](./refresh_logging.py) — Refresh diagnostic redaction.
- [refresh.py](./refresh.py) — Refresh exchange.
- [setup.py](./setup.py) — Metadata-only setup validation without registration or user authorization.
- [transport.py](./transport.py) — HTTP contracts and in-memory adapter.
- [validation.py](./validation.py) — Wire and provider-context validation.
