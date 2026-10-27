---
type: Software Module
title: "Workspace"
description: "Shared workspace navigation and fail-closed administration presentation resolution."
---

# Files

- [admin-access.ts](./admin-access.ts) — Administration navigation eligibility.
- [admin-access.test.ts](./admin-access.test.ts) — Access presentation tests.
- [navigation.ts](./navigation.ts) — Workspace destinations and labels.
- [workspace-access-state.svelte.ts](./workspace-access-state.svelte.ts) — Independent access lookup lifetime.
- [workspace-access-state.test.ts](./workspace-access-state.test.ts) — Access lookup isolation tests.

# Context not available from the code

- [ADR-005: One Workspace and Only Usable Controls](../../../../project/architecture-records/ADR-005-unified-workspace-and-usable-controls.md) — Navigation eligibility is not backend authorization.
