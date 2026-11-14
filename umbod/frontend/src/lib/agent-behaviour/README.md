---
type: Software Module
title: Agent behaviour administration
description: Validated configuration publication and self-reported diagnostic inspection.
---

# Files

- [API ports](api.ts) — Configuration, backend-owned defaults and report operations.
- [Schemas](domain/schemas.ts) — Validated wire contracts, configured memberships and collection limits.
- [Editing rules](domain/editing.ts) — Plain-language configuration validation feedback.
- [Schema tests](domain/schemas.test.ts) — Unicode bounds, duplicate values and retained reference shapes.
- [HTTP adapters](infrastructure/api.ts) — Configuration and report routes over the shared transport.
- [Adapter tests](infrastructure/api.test.ts) — Outbound validation, response parsing and report filters.
- [Configuration state](state/configuration-state.svelte.ts) — Pattern-first drafts, stable IDs, persistent reporting intent and conflict-safe save.
- [Reports state](state/reports-state.svelte.ts) — Draft and applied queries, reusable findings lifecycle, original snapshots and confirmed deletion.
- [Page state](state/page-state.svelte.ts) — Owner-managed configuration lifetime, published filter options, access revocation and disposal.
- [State tests](state/agent-behaviour.test.ts) — Pattern editing, reporting initialization and consent, limits, conflicts and asynchronous fences.
- [In-memory adapter](in-memory.test-support.ts) — Test-only API and deferred request support.
