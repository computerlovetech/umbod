---
type: Software Module
title: Personal access tokens
description: Validated personal access token management client and injectable contracts.
---

# Personal access tokens

- [API port](api.ts) — Token issuance, metadata listing and deletion-based revocation contracts.
- [Domain schemas](domain/README.md) — Validated token request and response shapes.
- [HTTP adapters](infrastructure/README.md) — Resource routes and browser composition over the shared transport.
- [In-memory test support](in-memory-api.test-support.ts) — Typed token management adapter for isolated feature tests.
