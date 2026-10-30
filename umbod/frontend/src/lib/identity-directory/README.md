---
type: Software Module
title: Identity directory client
description: Best-effort identity observation and server-scoped provider group discovery.
---

# Files

- [port.ts](./port.ts) — Observation, directory search and browser scheduling boundaries.
- [domain/schemas.ts](./domain/schemas.ts) — Validated directory responses and bounded search inputs.
- [api.ts](./api.ts) — Neutral composite client using the shared transport.
- [http-route.ts](./http-route.ts) — Bodyless observation and administrative group search adapters.
- [observation-coordinator.ts](./observation-coordinator.ts) — Nonblocking observation, retry and successful-attempt throttling.
- [browser-environment.ts](./browser-environment.ts) — Browser visibility, clock and periodic scheduling.
- [in-memory.test-support.ts](./in-memory.test-support.ts) — Test-only directory and observation adapter.
- [api.test.ts](./api.test.ts) — Port contract and HTTP validation tests.
- [observation-coordinator.test.ts](./observation-coordinator.test.ts) — Pending, retry, visibility and disposal tests.
- [ADR-012](../../../../project/architecture-records/ADR-012-login-observed-identity-directory.md) — Login-observed discovery boundaries.
