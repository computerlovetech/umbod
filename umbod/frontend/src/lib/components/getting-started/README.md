---
type: Software Module
title: Getting started components
description: Feature-owned MCP harness connection and installation guidance.
---

# Files

- [GettingStarted.svelte](./GettingStarted.svelte) — Harness connection content under the persistent workspace frame.
- [McpSetupGuide.svelte](./McpSetupGuide.svelte) — Harness installer wizard and command review.
- [installation-wizard-state.svelte.ts](./installation-wizard-state.svelte.ts) — Step transitions, telemetry selection, and expiring install command lifecycle.
- [telemetry-installer-availability.svelte.ts](./telemetry-installer-availability.svelte.ts) — Client-only telemetry eligibility for the wizard.
- [plugin-installation-state.svelte.ts](./plugin-installation-state.svelte.ts) — Platform and harness selection with single-URL Bash and PowerShell installation commands.
- [plugin-installation-state.svelte.test.ts](./plugin-installation-state.svelte.test.ts) — Target selection, exactly one installer URL, and shell quoting.
- [plugin-installation.dom.test.ts](./plugin-installation.dom.test.ts) — Wizard navigation, copyable commands, and on-demand telemetry claims.
- [installation-url.ts](./installation-url.ts) — Public API base resolution and credential-free HTTPS installer URL validation with loopback development support.
- [installation-url.test.ts](./installation-url.test.ts) — Deployment prefixes, loopback support, and unsafe installer URL rejection.
- [getting-started.test.ts](./getting-started.test.ts) — Installer-only workspace rendering and onboarding navigation.
- [mcp-setup.test.ts](./mcp-setup.test.ts) — Server-rendered initial wizard step without eager install details.
