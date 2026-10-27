---
type: Software Module
title: "Native tool runtime"
description: "Native exposure, discovery projections and lifecycle-owned reconciliation."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [native_capabilities.py](./native_capabilities.py) — Discovery and execution adapters.
- [ports.py](./ports.py) — Exposure and runtime-state contracts.
- [registry.py](./registry.py) — Tool exposure and reconciliation.
- [state.py](./state.py) — Runtime state.
- [synchronization.py](./synchronization.py) — Lifecycle change application.

# Context not available from the code

- [ADR-008](../../../../../../../../project/architecture-records/ADR-008-event-synchronized-tool-runtime.md) — Required event-synchronized discovery architecture; projections are not invocation authority and cross-worker updates are not instantaneous.
