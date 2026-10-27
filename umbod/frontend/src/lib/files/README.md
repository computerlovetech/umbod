---
type: Software Module
title: "User files"
description: "User filesystem contracts and browsing state independent of administration."
---

# Files

- [api.ts](./api.ts) — Filesystem port.
- [domain/](./domain/) — Filesystem validation contracts.
- [errors.ts](./errors.ts) — Safe read and creation failures.
- [files-api.test.ts](./files-api.test.ts) — Filesystem port and HTTP tests.
- [fixtures.test-support.ts](./fixtures.test-support.ts) — Test-only node fixtures.
- [infrastructure/](./infrastructure/) — Filesystem HTTP and in-memory adapters.
- [state/](./state/) — URL selection and folder creation state.

# Context not available from the code

- [ADR-006: Filesystem Infrastructure Boundary](../../../../project/architecture-records/ADR-006-filesystem-infrastructure-boundary.md) — Filesystem ownership and storage authority.
