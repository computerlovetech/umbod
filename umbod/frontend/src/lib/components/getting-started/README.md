---
type: Software Module
title: Getting started components
description: Feature-owned MCP connection guidance and personal telemetry setup.
---

# Files

- [GettingStarted.svelte](./GettingStarted.svelte) — Exclusive harness and telemetry subpages in the shared workspace and subpage container.
- [McpSetupGuide.svelte](./McpSetupGuide.svelte) — Harness-specific remote MCP connection instructions.
- [mcp-setup-state.svelte.ts](./mcp-setup-state.svelte.ts) — Endpoint-driven commands and Copilot configuration.
- [mcp-endpoint.ts](./mcp-endpoint.ts) — Absolute MCP endpoint resolution for origins and existing endpoint paths.
- [Telemetry setup API](../../telemetry-setup/README.md) — Instance-configured collector availability and endpoint discovery.
- [TelemetrySetup.svelte](./TelemetrySetup.svelte) — Token list with expiry dates, right-aligned delete icons and modal creation.
- [TelemetryTokenDialog.svelte](./TelemetryTokenDialog.svelte) — Native creation form and one-time harness configuration with shared controls.
- [telemetry-setup-state.svelte.ts](./telemetry-setup-state.svelte.ts) — Instance availability, duration-based expiry, issuance, token removal and transient secrets.
- [telemetry-formatters.ts](./telemetry-formatters.ts) — Logs-only harness configuration using the server-provided endpoint.
- [getting-started.test.ts](./getting-started.test.ts) — Exclusive subpage rendering, workspace headings and onboarding navigation.
- [mcp-setup.test.ts](./mcp-setup.test.ts) — Client guidance, escaped configuration and endpoint resolution tests.
- [telemetry-formatters.test.ts](./telemetry-formatters.test.ts) — Harness syntax and privacy settings tests.
- [telemetry-setup-state.test.ts](./telemetry-setup-state.test.ts) — Token lifecycle, failures and obsolete-result fencing tests.
- [telemetry-setup.dom.test.ts](./telemetry-setup.dom.test.ts) — Modal creation, copying, cancellation, active and revoked token deletion, and access eligibility interactions.
