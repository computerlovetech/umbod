---
type: Software Module
title: Personal MCP administration domain
description: Boundary schemas for personal connector policy and OAuth pre-publication setup.
---

# Files

- [schemas.ts](schemas.ts) — Personal registration, automatic public/confidential clients, issuer approval and revision-safe policy contracts.
- [schemas.test.ts](schemas.test.ts) — Automatic confidential methods, bounded issuer approval and credential-free request/response tests.
- [discovery.ts](discovery.ts) — Unsaved endpoint discovery, explicit issuer selection and backend-proposed automatic client contracts.
- [setup.ts](setup.ts) — Setup requests, discovery, validation, mismatch and bounded failure contracts.
- [availability.ts](availability.ts) — Deployment configuration projections for personal connector availability.
- [availability.test.ts](availability.test.ts) — Explicit availability and unknown-state behavior tests.
