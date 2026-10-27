---
type: Software Module
title: Core
description: Shared application workflows, domain contracts and feature-local adapters behind REST and MCP.
---

# Files

- [__init__.py](./__init__.py)
- [activation](./activation/README.md) — Capability enablement.
- [admin_overview](./admin_overview/README.md) — Administration summary contracts.
- [administrator](./administrator/) — Shared administrator configuration.
- [caching](./caching/README.md) — Request-local result reuse.
- [callers](./callers/README.md) — Transport-neutral caller facts.
- [capabilities](./capabilities/README.md) — Capability identity and catalogues.
- [configuration](./configuration/) — Encrypted connector configuration.
- [connectors](./connectors/) — Native, OpenAPI and downstream MCP connectors.
- [filesystem](./filesystem/README.md) — Namespaces, content and access policy.
- [groups](./groups/README.md) — Group catalogue.
- [icons](./icons/README.md) — Favicon discovery.
- [identity](./identity/) — Connector identity.
- [invocation](./invocation/) — Invocation policy and approval.
- [key_value](./key_value/README.md) — Key-value storage contracts.
- [messaging](./messaging/) — Events and stream contracts.
- [network](./network/) — Shared network validation.
- [permissions](./permissions/README.md) — Group grants and runtime access.
- [persistence](./persistence/README.md) — Database ports and read plans.
- [publishing](./publishing/README.md) — Connector publication.
- [signals](./signals/README.md) — Application-local signals.
- [telemetry](./telemetry/README.md) — Telemetry models and sink ports.
- [user_catalogue](./user_catalogue/README.md) — Caller-visible connector catalogue.

# Context not available from the code

- Shared root packages must not import connector-kind packages. Cross-kind composition belongs in delivery wiring.
- [ADR-001](../../../../project/architecture-records/ADR-001-backend-neutral-persistence.md) — Persistence boundary decisions.
- [ADR-009](../../../../project/architecture-records/ADR-009-deferred-read-planning.md) — Read planning and authority boundaries.
