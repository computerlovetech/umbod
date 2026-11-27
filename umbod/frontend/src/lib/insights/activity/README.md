---
type: Software Module
title: Personal activity
description: Owner-scoped activity reads and dashboard interaction state.
---

# Files

- [Activity API port](domain/activity-api.ts) — Overview, session listing, and session detail read operations.
- [Activity schemas](domain/activity-schemas.ts) — UTC periods, source availability, cursor pages, and verified response identity.
- [HTTP adapter](infrastructure/activity-api.ts) — Typed reads over the browser transport, including the overview's partial and unavailable states.
- [Activity state](activity-state.svelte.ts) — Source and period selection, switching between overview and session detail, and verified account reads.
- [Dashboard account scope](../../dashboard/state/dashboard-activity-state.svelte.ts) — Verified account observation and request suspension; preserves source and period for the same account.
- [Presentation](presentation.ts) — Harness client labels, composite card keys, and shared ranking projections.
- [Activity components](../../components/personal/activity/README.md) — Source-specific reports and session navigation.
