---
type: Software Module
title: Outbound HTTP
description: Shared asynchronous HTTP client creation and bounded JSON reads.
---

# Files

- [__init__.py](./__init__.py) — Public HTTP infrastructure exports.
- [client.py](./client.py) — Outbound client factory, connection options, and bounded JSON reads.
- [httpx_client.py](./httpx_client.py) — HTTPX wrapper for streaming, error translation, and cleanup.
- [HTTP port](../../core/network/http.py) — Library-neutral request, response, and client contracts.
