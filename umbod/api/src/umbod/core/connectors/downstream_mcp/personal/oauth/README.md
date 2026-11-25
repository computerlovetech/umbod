---
type: Software Module
title: Personal downstream MCP OAuth
description: OAuth policy, authorization and refresh for owner-scoped downstream connections.
---

# Files

- [applications/](./applications/README.md) — Shared confidential registrations and immutable personal grant references.
- [authorization/](./authorization/README.md) — Durable authorization attempts and orchestration.
- [configuration/](./configuration/README.md) — Personal OAuth policy, separate from shared connector authority.
- [grants/](./grants/README.md) — Saved grants and binding to current policy.
- [metadata/](./metadata/README.md) — Read-only creation discovery contracts and injected provider port.
- [refresh/](./refresh/README.md) — Token refresh reservation and orchestration.
- [setup/](./setup/README.md) — Nonsecret pre-publication discovery and validation receipts.
- [callback.py](./callback.py) — Callback route bindings.
- [diagnostics.py](./diagnostics.py) — OAuth failure observation port.
- [failures.py](./failures.py) — Immutable, sanitized provider failure evidence.
