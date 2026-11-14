---
type: Software Module
title: Getting started components
description: Feature-owned MCP connection guidance and personal telemetry setup.
---

# Files

- [GettingStarted.svelte](./GettingStarted.svelte) — Exclusive harness and telemetry subpages in the shared workspace and subpage container.
- [McpSetupGuide.svelte](./McpSetupGuide.svelte) — OS tabs, Codex and Claude Code installation commands, prerequisites, and script inspection.
- [plugin-installation-state.svelte.ts](./plugin-installation-state.svelte.ts) — Platform and harness selection with single-URL Bash and PowerShell installation commands.
- [plugin-installation-state.svelte.test.ts](./plugin-installation-state.svelte.test.ts) — Target selection, keyboard transitions, exactly one installer URL, and shell quoting.
- [plugin-installation.dom.test.ts](./plugin-installation.dom.test.ts) — OS/harness choices, clipboard wiring, keyboard focus, and absence of manual or post-install guides.
- [installation-url.ts](./installation-url.ts) — Public API base resolution and credential-free HTTPS installer URL validation with loopback development support.
- [installation-url.test.ts](./installation-url.test.ts) — Deployment prefixes, loopback support, and unsafe installer URL rejection.
- [Telemetry setup API](../../telemetry-setup/README.md) — Instance-configured collector availability and endpoint discovery.
- [TelemetrySetup.svelte](./TelemetrySetup.svelte) — Token list with expiry dates, right-aligned delete icons and modal creation.
- [TelemetryTokenDialog.svelte](./TelemetryTokenDialog.svelte) — Native creation form and one-time harness configuration with shared controls.
- [telemetry-setup-state.svelte.ts](./telemetry-setup-state.svelte.ts) — Instance availability, duration-based expiry, issuance, token removal and transient secrets.
- [telemetry-formatters.ts](./telemetry-formatters.ts) — Logs-only harness configuration using the server-provided endpoint.
- [getting-started.test.ts](./getting-started.test.ts) — Exclusive subpage rendering, workspace headings and onboarding navigation.
- [mcp-setup.test.ts](./mcp-setup.test.ts) — Installer-only rendering without explicit endpoint arguments or legacy guidance.
- [telemetry-formatters.test.ts](./telemetry-formatters.test.ts) — Harness syntax and privacy settings tests.
- [telemetry-setup-state.test.ts](./telemetry-setup-state.test.ts) — Token lifecycle, failures and obsolete-result fencing tests.
- [telemetry-setup.dom.test.ts](./telemetry-setup.dom.test.ts) — Modal creation, copying, cancellation, active and revoked token deletion, and access eligibility interactions.
