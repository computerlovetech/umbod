---
type: Software Module
title: Filesystem node updates
description: Authorized revision-checked name, placement and metadata changes for files and directories.
---

# Files

- [__init__.py](./__init__.py) — Public node changes, patches, service and protocol exports.
- [models.py](./models.py) — Shared strict REST and MCP changes with explicit omitted-field preservation.
- [ports.py](./ports.py) — Caller-aware eligibility and node update contract.
- [service.py](./service.py) — Atomic item and move-parent authorization, metadata merging and post-move flags even when discovery is lost.
