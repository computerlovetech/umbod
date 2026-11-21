---
type: Software Module
title: "Anonymous MCP endpoint access"
description: "Checks whether a public MCP endpoint accepts an anonymous Streamable HTTP initialize request."
---

# Files

- [__init__.py](./__init__.py) — Context-managed composition with the public-address-pinned connection pool.
- [adapter.py](./adapter.py) — Single HTTPS attempt with bounded reads and sanitized outcome mapping.
- [protocol.py](./protocol.py) — MCP initialize message and response validation for JSON and event streams.
- [Core port](../../core/connectors/downstream_mcp/endpoint_access.py) — Transport-independent access check contract.
