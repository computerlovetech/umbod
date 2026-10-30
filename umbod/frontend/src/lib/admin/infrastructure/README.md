---
type: Software Module
title: "Administration infrastructure"
description: "Browser transport, public runtime configuration and administration API composition."
---

# Files

- [admin-api.ts](./admin-api.ts) — Composite administration client.
- [browser-request.ts](./browser-request.ts) — Client failure presentation.
- [logout.ts](./logout.ts) — Logout navigation port and adapters.
- [logout.test.ts](./logout.test.ts) — Logout navigation tests.
- [public-configuration.ts](./public-configuration.ts) — Public configuration boundary.
- [public-configuration.test.ts](./public-configuration.test.ts) — Configuration validation tests.
- [schema.ts](./schema.ts) — Shared validation helpers.
- [transport.ts](./transport.ts) — Authenticated JSON, multipart and raw-File transport, validated strong opaque conditional headers and header responses.
- [transport.spec.ts](./transport.spec.ts) — Transport tests.
- [Sharing transport regressions](../../files/sharing-api.test.ts) — Conditional JSON replacement and malformed If-Match rejection before network I/O.
