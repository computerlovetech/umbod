---
type: Software Module
title: Workspace infrastructure
description: Workspace profile adapters over the shared authenticated transport.
---

# Files

- [profile-route.ts](./profile-route.ts) — Neutral current-profile GET route with response validation.
- [workspace-api.ts](./workspace-api.ts) — Composite workspace client using the existing configured transport.
- [profile-route.test.ts](./profile-route.test.ts) — Transport contract, configured base paths and ordinary identity without privileged requests.
