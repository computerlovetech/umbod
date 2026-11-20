---
type: Software Module
title: MCP Registry
description: Provider-independent search contracts for discovering remote MCP servers.
---

# Files

- [__init__.py](./__init__.py) — Public lookup contracts.
- [models.py](./models.py) — Search criteria, compatible server candidates, and pages; an empty cursor denotes the first or last page.
- [ports.py](./ports.py) — Asynchronous search port and provider-independent failure.
