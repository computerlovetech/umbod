---
type: Software Module
title: "Filesystem administration"
description: "Ports and adapters for root filesystem group access policy."
---

# Files

- [administration.test.ts](./administration.test.ts) — Policy port and HTTP tests.
- [domain/](./domain/) — Strict group-only root access request and response contracts.
- [errors.ts](./errors.ts) — Safe policy failure presentation.
- [fixtures.test-support.ts](./fixtures.test-support.ts) — Policy test fixtures.
- [http-route.ts](./http-route.ts) — Root access HTTP adapter.
- [in-memory.ts](./in-memory.ts) — Revision-aware policy adapter with blocked group assignment checks.
- [port.ts](./port.ts) — Policy administration port.
