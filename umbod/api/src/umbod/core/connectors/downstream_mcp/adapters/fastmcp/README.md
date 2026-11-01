---
type: Software Module
title: "FastMCP downstream integration"
description: "Transport, discovery and SDK OAuth adapters for downstream MCP connections."
---

# Files

- [__init__.py](./__init__.py) — Module boundary.
- [client.py](./client.py) — Invocation client construction.
- [connection.py](./connection.py) — Authentication strategies and explicit OAuth storage-mode selection.
- [discovery.py](./discovery.py) — Discovery probe orchestration.
- [oauth.py](./oauth.py) — SDK OAuth provider policy and serialized authorization flows.
- [oauth_client.py](./oauth_client.py) — Interactive OAuth client transport.
- [oauth_session.py](./oauth_session.py) — Disposable authorization and refresh sessions.
- [oauth_storage.py](./oauth_storage.py) — SDK authorization document and shared storage contract.
- [oauth_storage_adapters.py](./oauth_storage_adapters.py) — Detached document storage and persisted compare-and-swap authorization storage.
- [probe.py](./probe.py) — Capability collection, safe redirects and authorization export.
