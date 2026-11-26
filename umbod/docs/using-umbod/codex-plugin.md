# Codex CLI plugin

Use this plugin to connect Codex CLI to an existing Umbod deployment. Before directing users to **Getting started**, check that the page advertises the intended public MCP endpoint and that sign-in is configured for that origin. The plugin installs per user through a local marketplace; it does not install the server or copy credentials into Codex.

The package includes the remote MCP connection and skills for connected-app access, user-requested diagnostics, and obstacle reporting. Both reporting paths require the administrator to enable diagnostic reporting and use the live Umbod playbook. Agents must follow the collection instructions and respect user and client policy; Umbod does not verify whether the user requested a report.

Local-marketplace installation was verified with Codex CLI 0.167.0. Update Codex if `codex plugin` is unavailable. An OpenAI public-directory submission and ChatGPT desktop are not required.

## Install from Getting started

The built-in installer is not included in Umbod `0.0.1-beta.9`. If your workspace does not show **Connect your harness**, configure your client to use the [ordinary MCP endpoint](../operations/service-topology.md) instead.

Direct users to **Getting started → Connect your harness** to select their operating system and **Codex**, then copy and run the installation command. macOS and Linux use Bash with Python 3.8 or later and curl. Native Windows uses PowerShell 5.1 or later with its included .NET runtime; no separate download or hashing utility is required. Codex must already be installed. Use the Linux choice inside WSL.

The command contains a single installer URL. Its script already includes the instance's package location, MCP endpoint and selected harness, so no additional configuration arguments are needed. The installer downloads a credential-free package, verifies its checksum and endpoint, stores it in a persistent user-owned directory, registers the marketplace, and installs the plugin. Administrator access is not required. **Inspect installer** opens the same configured script before you run it.

### Check the connection

Restart Codex, open `/mcp`, and sign in with your Umbod account if prompted. Verify that Codex discovers a published tool your account is allowed to use; no write is needed. A telemetry token cannot sign in to MCP.

### Optional: send Codex logs to Umbod

If **Set up telemetry** is available in the installer, choose **With telemetry** before copying the command. In the terminal, review the proposed log exporter settings and choose whether to save Umbod as the Codex default. If you decline, your telemetry settings are unchanged. Treat the one-time install command as a credential; do not share it.

## Existing installations

An identical installer rerun verifies the existing package and plugin registration without creating duplicates. Existing standalone Umbod MCP connections, conflicting marketplaces, disabled plugins, and modified package files stop installation with guidance for manual review. The installer does not remove or replace unrelated configuration.

The installer does not upgrade an existing registration in place. To pick up a changed package, use Codex's `/plugins` interface to uninstall the Umbod plugin for that instance, remove only its matching Umbod marketplace registration, then rerun the installation command from Getting started and restart Codex. Leave other marketplaces and MCP entries untouched.

## Troubleshooting

- **Wrong endpoint:** check the deployment's public MCP configuration. The installer refuses packages that disagree with the endpoint advertised by Getting started.
- **Sign-in fails:** inspect `/mcp` and the deployment's OAuth discovery and public-origin configuration. The package does not implement a separate authentication service.
- **No skill appears:** start a new session and confirm the plugin is enabled in `/plugins`.
- **No tools match:** verify that the administrator published tools and granted your account access. Do not work around missing permissions using another access method.
- **Server unavailable:** restore connectivity to the configured deployment. Plugin installation does not start Umbod or establish a tunnel.

## Package development

The [repository package builder](https://github.com/computerlovetech/umbod/blob/main/umbod/scripts/build_codex_plugin.py) creates a new endpoint-specific Codex marketplace directory and prints registration commands without executing them. It uses the [shared package renderer](https://github.com/computerlovetech/umbod/blob/main/umbod/api/src/umbod/core/harness_plugins/rendering.py), canonical connected-app, agent-behaviour, and run-diagnostics skills, and repository license. Existing output directories are never replaced.

Edit `skills/integrations/umbod-connected-apps/SKILL.md`, `skills/integrations/umbod-agent-behaviour/SKILL.md`, and `skills/integrations/run-diagnostics/SKILL.md` in the repository root to maintain the packaged skills. The shared API packages canonical resources directly; there is no browser-generated ZIP or frontend package template to regenerate.

## References

- [Codex plugins](https://developers.openai.com/codex/plugins) — Supported CLI installation and plugin lifecycle.
- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins) — Manifest, local-marketplace, and MCP configuration contracts.
- [Connect to Umbod](../operations/service-topology.md) — Umbod's public and private service boundaries.
- [Harness installation configuration](../operations/configuration.md#harness-plugin-installation) — Public artifact routing, prerequisites, and endpoint authority.
