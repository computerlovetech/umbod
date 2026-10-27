---
type: Software Module
title: "Native tool discovery"
description: "Search and manifest adapters for native and OpenAPI capability discovery."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [manifest.py](./manifest.py) — Connector-domain manifests.
- [openapi.py](./openapi.py) — OpenAPI search adaptation.
- [search.py](./search.py) — Candidate ranking contracts.
- [tools.py](./tools.py) — Search and manifest registration.

# Context not available from the code

- [ADR-008](../../../../../../../../project/architecture-records/ADR-008-event-synchronized-tool-runtime.md) — Required event-synchronized discovery architecture; projections are not invocation authority and cross-worker updates are not instantaneous.
