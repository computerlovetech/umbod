---
type: Software Module
title: Settings components
description: Personal token management and one-time telemetry configuration.
---

# Files

- [Telemetry setup API](../../telemetry-setup/README.md) — Instance-configured collector availability and endpoint discovery.
- [PersonalTokens.svelte](./PersonalTokens.svelte) — Token list with actual scopes, scope filtering, expiry dates, and actions.
- [TelemetryTokenDialog.svelte](./TelemetryTokenDialog.svelte) — Native creation form and one-time harness configuration with shared controls.
- [telemetry-setup-state.svelte.ts](./telemetry-setup-state.svelte.ts) — Scope filtering, telemetry availability, token lifecycle and transient secrets.
- [telemetry-formatters.ts](./telemetry-formatters.ts) — Logs-only harness configuration using the server-provided endpoint.
- [telemetry-formatters.test.ts](./telemetry-formatters.test.ts) — Harness syntax and privacy settings tests.
- [telemetry-setup-state.test.ts](./telemetry-setup-state.test.ts) — Token lifecycle, failures and obsolete-result fencing tests.
- [telemetry-setup.dom.test.ts](./telemetry-setup.dom.test.ts) — Scope filtering, modal creation, configuration copying, token deletion, and access eligibility.
