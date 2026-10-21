# Personal connections

**Module responsibility:** Owner-scoped personal MCP selection, local authorization health, explicit renewal, authorization attempts and tool discovery, independent of administration state.

- `domain/schemas.ts` validates exact selection, request and OAuth wire contracts, including the six-state local authorization health union, strict renewal bodies and discovery-required renewal results, and HTTPS authorization links.
- `api.ts` defines selection and authorization ports with no caller-supplied owner identity.
- `infrastructure/in-memory-api.ts` provides a validated in-memory port adapter with explicitly seeded health facts, never inferred from selection authorization presence.
- `infrastructure/*-route.ts` implements resource routes over the shared generic Transport; `personal-connections-api.ts` composes them with browser transport and public configuration only.
- `state/` contains page-lifetime reactive state, safe error presentation, explicit actions and stale-result guards.

Reads never enable, authorize or discover. Known attempt identifiers and authorization URLs stay in page memory and are cleared on terminal outcomes or disposal. Status checks are manual; successful completion, renewal and explicit discovery reload selection and local health. Renewal never triggers discovery. An uncertain mutation requires an explicit safe details refresh before further mutation. Saved authorization, local authorization health, enablement and runtime eligibility are separate facts. Health is a database-only read, not a live provider probe. Unavailable or uncertain status blocks renewal and discovery until a manual status check succeeds; refreshing status never authorizes client-clock-based retries. Generation guards reject late health, renewal, selection and attempt results after superseding actions or disposal.
