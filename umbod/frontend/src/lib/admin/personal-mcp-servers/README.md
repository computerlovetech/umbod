---
type: Software Module
title: Personal MCP administration contracts
description: Validated personal server registration, revision-safe policy editing and pre-publication OAuth setup ports.
---

# Files

- [Domain contracts](domain/README.md) — Policy, endpoint, scope and setup status schemas.
- [administration.ts](administration.ts) — Injectable personal server and policy administration port.
- [http-route.ts](http-route.ts) — Transport-backed registration and revision-safe policy adapter.
- [setup-administration.ts](setup-administration.ts) — Saved setup, explicit discovery and validation port.
- [setup-route.ts](setup-route.ts) — Validated setup HTTP routes without automatic replay.
- [setup-route.test.ts](setup-route.test.ts) — Request validation, safe response boundaries and route dispatch tests.
- [setup.test-support.ts](setup.test-support.ts) — Test-only setup adapter with policy binding and setup revision checks.
- [in-memory.ts](in-memory.ts) — In-memory personal server administration adapter.
- [administration.test.ts](administration.test.ts) — Policy changes, publication withdrawal and credential boundary tests.
- [http-route.test.ts](http-route.test.ts) — Registration and policy HTTP adapter tests.
- [fixtures.test-support.ts](fixtures.test-support.ts) — Personal connector and policy test fixtures.
- [availability.test-support.ts](availability.test-support.ts) — Deployment availability test fixtures.
