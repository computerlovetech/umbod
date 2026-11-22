---
type: Software Module
title: Getting started components
description: Feature-owned MCP harness connection and installation guidance.
---

# Files

- [GettingStarted.svelte](./GettingStarted.svelte) — Harness connection content under the persistent workspace frame.
- [McpSetupGuide.svelte](./McpSetupGuide.svelte) — Four-step harness installation wizard with prerequisites, script inspection and private package download.
- [installation-wizard-state.svelte.ts](./installation-wizard-state.svelte.ts) — Step transitions, Claude Code telemetry selection, and current package lifecycle.
- [telemetry-installer.ts](./telemetry-installer.ts) — Feature port for preparing a private installer package.
- [installer-artifact.ts](./installer-artifact.ts) — Bounded public installer retrieval and private telemetry payload packaging.
- [prepare-telemetry-installer.ts](./prepare-telemetry-installer.ts) — Scoped token issuance after validation of the collector and installer.
- [prepare-telemetry-installer.test.ts](./prepare-telemetry-installer.test.ts) — Private artifact contents, pre-issuance validation, and cancellation.
- [telemetry-installer-availability.svelte.ts](./telemetry-installer-availability.svelte.ts) — Client-only telemetry eligibility for the wizard.
- [plugin-installation-state.svelte.ts](./plugin-installation-state.svelte.ts) — Platform and harness selection with single-URL Bash and PowerShell installation commands.
- [plugin-installation-state.svelte.test.ts](./plugin-installation-state.svelte.test.ts) — Target selection, exactly one installer URL, and shell quoting.
- [plugin-installation.dom.test.ts](./plugin-installation.dom.test.ts) — Wizard navigation, copyable commands, and eligible private-package preparation and download.
- [installation-url.ts](./installation-url.ts) — Public API base resolution and credential-free HTTPS installer URL validation with loopback development support.
- [installation-url.test.ts](./installation-url.test.ts) — Deployment prefixes, loopback support, and unsafe installer URL rejection.
- [getting-started.test.ts](./getting-started.test.ts) — Installer-only workspace rendering and onboarding navigation.
- [mcp-setup.test.ts](./mcp-setup.test.ts) — Server-rendered initial wizard step without eager install details.
