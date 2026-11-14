# Codex CLI plugin

The Umbod plugin bundles a remote MCP connection and a skill for discovering and using connected apps. It connects to an existing Umbod deployment; it does not install the Umbod server or copy credentials into Codex.

This local-marketplace installation is verified with Codex CLI 0.167.0. Update Codex if `codex plugin` is unavailable. It does not require an OpenAI public-directory submission or a ChatGPT desktop installation.

## Install from Getting started

Open **Getting started → Connect your harness**, select your operating system and **Codex**, then copy and run the installation command. macOS and Linux use Bash with Python 3.8 or later and curl. Native Windows uses PowerShell 5.1 or later and curl.exe. Codex must already be installed. Use the Linux choice inside WSL.

The command contains a single installer URL. Its script already includes the instance's package location, MCP endpoint and selected harness, so no additional configuration arguments are needed. The installer downloads a credential-free package, verifies its checksum and endpoint, stores it in a persistent user-owned directory, registers the marketplace, and installs the plugin. Administrator access is not required. **Inspect installer** opens the same configured script before you run it.

After verifying the installed plugin, the terminal displays the Umbod icon and numbered next steps for restarting Codex, opening `/mcp`, signing in when prompted, and discovering connected apps. These steps appear in the terminal rather than on the Getting started page.

Installation does not authenticate or verify connected-app access. Complete any requested sign-in using your normal Umbod account. Telemetry tokens do not authenticate MCP. Empty discovery results can mean no matching published tools are available to your account; they do not necessarily mean authentication failed. Do not run write operations merely to test installation.

## Existing installations

An identical installer rerun verifies the existing package and plugin registration without creating duplicates. Existing standalone Umbod MCP connections, conflicting marketplaces, disabled plugins, and modified package files stop installation with guidance for manual review. The installer does not remove or replace unrelated configuration.

Keep the installed marketplace directory in place. Use Codex's `/plugins` interface to inspect, disable, or uninstall the plugin. Review the registered marketplace before removing its source; do not delete unrelated Codex configuration or change connector permissions as part of removal.

## Troubleshooting

- **Wrong endpoint:** check the deployment's public MCP configuration. The installer refuses packages that disagree with the endpoint advertised by Getting started.
- **Sign-in fails:** inspect `/mcp` and the deployment's OAuth discovery and public-origin configuration. The package does not implement a separate authentication service.
- **No skill appears:** start a new session and confirm the plugin is enabled in `/plugins`.
- **No tools match:** verify that the administrator published tools and granted your account access. Do not work around missing permissions using another access method.
- **Server unavailable:** restore connectivity to the configured deployment. Plugin installation does not start Umbod or establish a tunnel.

## Package development

The [repository package builder](https://github.com/computerlovetech/umbod/blob/main/umbod/scripts/build_codex_plugin.py) creates a new endpoint-specific Codex marketplace directory and prints registration commands without executing them. It uses the [shared package renderer](https://github.com/computerlovetech/umbod/blob/main/umbod/api/src/umbod/core/harness_plugins/rendering.py), canonical connected-app skill, and repository license. Existing output directories are never replaced.

Edit `skills/integrations/umbod-connected-apps/SKILL.md` in the repository root to maintain the packaged skill. The shared API packages canonical resources directly; there is no browser-generated ZIP or frontend package template to regenerate.

## References

- [Codex plugins](https://developers.openai.com/codex/plugins) — Supported CLI installation and plugin lifecycle.
- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins) — Manifest, local-marketplace, and MCP configuration contracts.
- [Endpoints and ports](../reference/endpoints-and-ports.md) — Umbod's public and private service boundaries.
- [Harness installation configuration](../operations/configuration.md#harness-plugin-installation) — Public artifact routing, prerequisites, and endpoint authority.
