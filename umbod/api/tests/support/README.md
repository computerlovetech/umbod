---
type: Software Module
title: Backend test support
description: Test-only adapters and acceptance drivers for backend behavior tests.
---

# Files

- [activation.py](./activation.py) — In-memory capability activation store.
- [admin_overview.py](./admin_overview.py) — In-memory administration snapshot reader.
- [administrator_configuration.py](./administrator_configuration.py) — In-memory administrator connector configuration catalogue.
- [approval_nonces.py](./approval_nonces.py) — In-memory approval nonce consumption.
- [configuration.py](./configuration.py) — In-memory current configurations and unavailable-secret adapter.
- [connector_capabilities.py](./connector_capabilities.py) — Connector capability test support.
- [connector_plugins.py](./connector_plugins.py) — Connector plugin test support.
- [filesystem](./filesystem/) — Filesystem acceptance drivers, policy decoding failures, and test adapters.
- [groups.py](./groups.py) — In-memory group catalogue with transactional rollback.
- [icons.py](./icons.py) — Scripted favicon HTTP and discovery adapters.
- [messaging.py](./messaging.py) — In-memory event stream, factory, and database event append failure injection.
- [native_tool_states.py](./native_tool_states.py) — Native tool state test support.
- [normalized_log_v1.json](./normalized_log_v1.json) — Frozen canonical version-1 evidence for backward-read, replay and persistence checks.
- [persistence_contracts.py](./persistence_contracts.py) — Backend-neutral records, schemas and operations shared by kernel and adapter contracts.
- [persistence_processes.py](./persistence_processes.py) — Spawn-safe SQLite claim and insert workers for process coordination checks.
- [personal_oauth.py](./personal_oauth.py) — Real memory persistence and explicit OAuth policy with production REST assembly.
- [rest_metrics.py](./rest_metrics.py) — In-memory REST request metrics.
- [signals.py](./signals.py) — Captured signal receiver failures.
- [sqlite_boundaries.py](./sqlite_boundaries.py) — AST-based test classification and SQLite boundary diagnostics.
- [telemetry_analytics.py](./telemetry_analytics.py) — In-memory telemetry aggregation reader and normalized log inputs.
- [telemetry_runtime.py](./telemetry_runtime.py) — Real memory database-backed analytics ingestion, query, and lifecycle support.
- [tool_configuration.py](./tool_configuration.py) — In-memory tool configuration mutations and policy revisions.
- [user_profiles.py](./user_profiles.py) — Fixed user profile provider.
