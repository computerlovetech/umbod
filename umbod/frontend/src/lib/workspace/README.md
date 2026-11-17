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
- [profile-identity.ts](./profile-identity.ts) — Trusted opaque profile identity keys mapped to account request fences without changing displayed user fields.
- [admin-access.ts](./admin-access.ts) — Capability-based navigation eligibility with independent visible identity.
- [admin-access.test.ts](./admin-access.test.ts) — Access presentation tests.
- [navigation.ts](./navigation.ts) — Separate workspace and administration destinations, sidebar labels, icons and route matching.
- [navigation.test.ts](./navigation.test.ts) — Eligible entry points, administration order and preview icon assignments.
- [navigation-history.svelte.ts](./navigation-history.svelte.ts) — Root-owned successful workspace location history and directional sidebar transitions.
- [navigation-history-context.ts](./navigation-history-context.ts) — Application-scoped navigation history composition for workspace shells.
- [navigation-history.test.ts](./navigation-history.test.ts) — Safe return locations, isolated lifetimes and context-only transition rules.
- [workspace-access-state.svelte.ts](./workspace-access-state.svelte.ts) — Frame-owned access lookup and source epochs fencing obsolete profile results.
- [workspace-context.ts](./workspace-context.ts) — Typed context requiring an explicitly mounted workspace frame.
- [workspace-scope.svelte.ts](./workspace-scope.svelte.ts) — Scoped page disposal and reactive identity inputs with per-consumer source-change detection.
- [workspace-navigation-state.svelte.ts](./workspace-navigation-state.svelte.ts) — Active workspace destination derived directly from the current pathname.
- [workspace-access-state.test.ts](./workspace-access-state.test.ts) — Access lookup isolation tests.

# Architecture

- [ADR-005: One Workspace and Only Usable Controls](../../../../project/architecture-records/ADR-005-unified-workspace-and-usable-controls.md) — Navigation eligibility is not backend authorization.
