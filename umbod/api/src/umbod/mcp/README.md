---
type: Software Module
title: "MCP boundary"
description: "MCP application composition, capability exposure, authentication and protocol observability."
---

# Files

- [__init__.py](./__init__.py) — Package exports.
- [administrator/](./administrator/) — Administrator capabilities.
- [agent_instructions.py](./agent_instructions.py) — Agent setup guidance resource.
- [assets/](./assets/) — MCP assets.
- [auth/](./auth/) — Authentication and caller capture.
- [authorization.py](./authorization.py) — FastMCP permission bridge.
- [connectors/](./connectors/) — Connector-kind delivery adapters.
- [context.py](./context.py) — Runtime context.
- [filesystem/](./filesystem/README.md) — Filesystem browsing and empty creation.
- [listeners/](./listeners/README.md) — Invocation observation adapters.
- [live_permission_updates.py](./live_permission_updates.py) — Permission synchronization.
- [logging/](./logging/) — Invocation and audit logging.
- [main.py](./main.py) — Service entrypoint delegation.
- [messaging/](./messaging/README.md) — Event replay and runtime synchronization.
- [metrics/](./metrics/README.md) — Invocation and protocol metrics.
- [middleware/](./middleware/README.md) — Protocol middleware.
- [proxies.py](./proxies.py) — Deferred runtime bindings.
- [public_app.py](./public_app.py) — Application assembly and lifespan.
- [runtime_adapters.py](./runtime_adapters.py) — Explicit production construction for injected invocation adapters.
- [runtime_options.py](./runtime_options.py) — Runtime composition options.
- [settings.py](./settings.py) — MCP settings.
- [signals/](./signals/README.md) — Neutral execution events.
- [tools/](./tools/) — Observed internal tool registration.

# Architecture

- [ADR-008](../../../../project/architecture-records/ADR-008-event-synchronized-tool-runtime.md) — Event-synchronized discovery and operation-scoped invocation authority.
- [Hosting boundary](../hosting/README.md) — Supported embedding API.
