---
type: Software Module
title: Personal activity
description: Owner-scoped read facade for separate harness and MCP activity summaries.
---

# Files

- [models.py](./models.py) — Activity summaries, source availability, harness session keys, and paging contracts.
- [ports.py](./ports.py) — Reader boundaries for harness telemetry and MCP usage.
- [service.py](./service.py) — Shared UTC windows, independent source results, and harness session queries.
- [cursor.py](./cursor.py) — Session pagination tokens bound to the account, period, and search.
