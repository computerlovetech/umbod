---
type: Software Module
title: "Dashboard"
description: "User catalogue contracts and dashboard lifetime independent of administration."
---

# Files

- [api.ts](./api.ts) — User catalogue port.
- [domain/](./domain/) — Catalogue validation contracts.
- [infrastructure/](./infrastructure/) — Catalogue HTTP and in-memory adapters.
- [presentation.ts](./presentation.ts) — Connector labels and sidebar identities.
- [state/](./state/) — Catalogue lifetime and capability search.
- [test-fixtures.ts](./test-fixtures.ts) — Catalogue test fixtures.

# Context not available from the code

- Catalogue tool schema changes require coordinated backend/frontend deployment because older strict clients reject additional tool fields.
