---
type: Software Module
title: Administrator system settings
description: Typed administration of instance-wide settings and their sources.
---

# Files

- [routes.py](./routes.py) — Register each new section's concrete router here.
- [filesystem.py](./filesystem.py) — Filesystem request and response contracts.
- [provider_group_mappings.py](./provider_group_mappings.py) — Whole-list mappings resource and indexed validation errors.
- [dependencies.py](./dependencies.py) — Trusted administrator access and request-scoped service composition.
- [System settings defaults](../../config/system_settings.py) — Read-only defaults from the startup configuration.
- [route_policy.py](./route_policy.py) — Section error handling and cache policy.
