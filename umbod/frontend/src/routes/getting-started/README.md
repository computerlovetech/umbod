---
type: Software Module
title: Getting started route
description: Single workspace destination for harness connection and telemetry onboarding.
---

# Files

- [+page.svelte](./+page.svelte) — Thin composition of the unified Getting started page.
- [+layout.ts](./+layout.ts) — Resolve the configured MCP endpoint for every onboarding subpage without administrator access.
- [layout.test.ts](./layout.test.ts) — Onboarding loader independence from privileged profile reads.
- [Telemetry](./telemetry/README.md) — Dedicated token-management subpage.
- [Getting started components](../../lib/components/getting-started/README.md) — MCP instructions, token management and harness configuration.
