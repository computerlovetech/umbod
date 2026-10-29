---
type: Software Module
title: "Downstream MCP persistence"
description: "Neutral encrypted stores, atomic lifecycle mutations and credential-free personal discovery snapshots."
---

# Files

- [factory.py](./factory.py) — Application-scoped store bundle composition.
- [ports.py](./ports.py) — Shared connector persistence contracts.
- [schema.py](./schema.py) — Definition, credential, connection and catalogue tables.
- [definitions.py](./definitions.py) — Connector definition persistence.
- [credentials.py](./credentials.py) — Encrypted shared credentials.
- [catalogs.py](./catalogs.py) — Shared tool catalogue persistence.
- [health.py](./health.py) — Shared connector health.
- [discovery_generation.py](./discovery_generation.py) — Aggregate discovery revision tracking.
- [personal_connections.py](./personal_connections.py) — Owner connection mutations and projection maintenance.
- [personal_connection_records.py](./personal_connection_records.py) — Encrypted owner connection decoding and ownership validation.
- [personal_discovery_schema.py](./personal_discovery_schema.py) — Sanitized owner availability table.
- [personal_discovery_projection.py](./personal_discovery_projection.py) — Write-time credential validation and secret-free availability states.
- [personal_tool_discovery.py](./personal_tool_discovery.py) — One read-only owner snapshot using supplied runtime definitions.
- [personal_tool_access.py](./personal_tool_access.py) — Authoritative serialized admission and private observation writes.
- [personal_tool_policies.py](./personal_tool_policies.py) — Administrator tool contracts.
- [personal_tools_schema.py](./personal_tools_schema.py) — Private observations and administrator policy tables.
- [personal_runtime_authorizations.py](./personal_runtime_authorizations.py) — Operation-scoped credential retrieval and current authority checks.
- [personal_oauth_attempts.py](./personal_oauth_attempts.py) — Durable OAuth attempts and atomic connection installation.
- [personal_oauth_schema.py](./personal_oauth_schema.py) — OAuth attempt table.
- [personal_oauth_configurations.py](./personal_oauth_configurations.py) — OAuth policy lifecycle and owner invalidation.
- [personal_oauth_configuration_schema.py](./personal_oauth_configuration_schema.py) — OAuth configuration table.
- [personal_refresh.py](./personal_refresh.py) — Refresh state transitions, availability projection and atomic events.
- [personal_refresh_records.py](./personal_refresh_records.py) — Encrypted refresh records and deadline semantics.
- [personal_refresh_schema.py](./personal_refresh_schema.py) — Refresh claim table.
- [personal_authorization_rejections.py](./personal_authorization_rejections.py) — Durable authorization rejection and projection invalidation.
- [personal_authorization_rejection_records.py](./personal_authorization_rejection_records.py) — Rejection records, credential fingerprints and matching or clearing helpers.
- [personal_authorization_health.py](./personal_authorization_health.py) — Owner-facing authorization health.
- [personal_authorization_health_schema.py](./personal_authorization_health_schema.py) — Authorization rejection table.
- [queries.py](./queries.py) — Neutral query helpers.
- [reads.py](./reads.py) — Shared persisted definition and catalogue reads.
