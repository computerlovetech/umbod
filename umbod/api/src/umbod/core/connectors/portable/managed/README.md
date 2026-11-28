---
type: Software Module
title: Managed portable connectors
description: Exact-revision submissions and inactive administrator-owned portable configuration.
---

# Submission

- [service.py](./service.py) — Authorizes and validates an exact revision before creating an inactive handoff.
- [models.py](./models.py) — Submission provenance and receipt contracts.
- [store.py](./store.py) — Atomic handoff persistence and same-revision receipt lookup.

# Administration

- [catalog.py](./catalog.py) — Lists inactive handoffs and validates complete replacements against their pinned fields.
- [catalog_models.py](./catalog_models.py) — Administrator summaries, form descriptors, and saved or unconfigured state.
- [catalog_store.py](./catalog_store.py) — Reads inventory and persists configuration without exposing submission provenance.
- [configuration_schema.py](./configuration_schema.py) — Admits the supported noncredential schema subset and projects pinned field descriptors.
- [ports.py](./ports.py) — Persistence contracts and safe failure states for submission and administration.
- [schema.py](./schema.py) — Neutral schemas and projections for immutable submissions and separate saved values.
