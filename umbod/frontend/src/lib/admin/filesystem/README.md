---
type: Software Module
title: "Filesystem administration"
description: "Shared namespace administration ports, schemas and validated HTTP adapters."
---

# Files

- [domain/namespaces.ts](./domain/namespaces.ts) — Strict shared namespace summaries, exact group grants and revision-safe mutation schemas.
- [namespaces-port.ts](./namespaces-port.ts) — Shared namespace administration port, separate from content access.
- [namespaces-route.ts](./namespaces-route.ts) — Validated shared namespace listing, creation and revision-safe replacement adapter.
- [namespaces-route.test.ts](./namespaces-route.test.ts) — Transport-port request contracts and invalid authority-bearing input tests.
- [Namespace test support](../../../../tests/support/filesystem/README.md) — Test-only revision-aware shared namespace adapter outside the application source.
