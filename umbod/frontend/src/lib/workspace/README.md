---
type: Software Module
title: "Workspace"
description: "Neutral authenticated profile, workspace navigation and capability-based administration presentation."
---

# Files

- [api.ts](./api.ts) — Neutral authenticated profile ports.
- [Domain](./domain/README.md) — Profile identity and explicit capability validation.
- [Infrastructure](./infrastructure/README.md) — Profile HTTP route and composite workspace client.
- [in-memory-api.test-support.ts](./in-memory-api.test-support.ts) — Test-only validated profile adapter.
- [admin-access.ts](./admin-access.ts) — Capability-based navigation eligibility with independent visible identity.
- [admin-access.test.ts](./admin-access.test.ts) — Access presentation tests.
- [navigation.ts](./navigation.ts) — Workspace destinations, labels and shell-owned route matching.
- [workspace-access-state.svelte.ts](./workspace-access-state.svelte.ts) — Independent access lookup lifetime.
- [workspace-access-state.test.ts](./workspace-access-state.test.ts) — Access lookup isolation tests.

# Architecture

- [ADR-005: One Workspace and Only Usable Controls](../../../../project/architecture-records/ADR-005-unified-workspace-and-usable-controls.md) — Navigation eligibility is not backend authorization.
