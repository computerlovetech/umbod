---
type: Software Module
title: "Authorized filesystem browsing"
description: "Caller-aware root discovery, node summaries and filtered child listing."
---

# Files

- [__init__.py](./__init__.py) — Public module exports.
- [models.py](./models.py) — Safe node summaries.
- [ports.py](./ports.py) — Browsing contract.
- [service.py](./service.py) — Authorized browsing and summary projection.

# Context

Do not put secrets in metadata expecting READ permission to protect them: DISCOVER exposes all custom metadata attributes. This boundary does not promise atomic check/use or mid-operation revocation.
