# Codex CLI plugin

The Umbod plugin bundles a remote MCP connection and a skill for discovering and using connected apps. It connects to an existing Umbod deployment; it does not install the Umbod server or copy credentials into Codex.

This local-marketplace installation is verified with Codex CLI 0.167.0. Update Codex if `codex plugin` is unavailable. It does not require an OpenAI public-directory submission or a ChatGPT desktop installation.

## Build the marketplace

Use a checkout of the Umbod repository and Python 3.10 or newer. From the repository root, copy the MCP endpoint from **Getting started** in your Umbod dashboard, then enter it when the first command waits for input:

```sh
read -r UMBOD_MCP_ENDPOINT
python3 umbod/scripts/build_codex_plugin.py \
  --endpoint "$UMBOD_MCP_ENDPOINT" \
  --output "$HOME/.local/share/umbod/codex-marketplace"
```

The builder creates a new directory and prints two installation commands. It never runs Codex, changes account settings, or replaces an existing directory. A deployment origin or path prefix is accepted; `/mcp` is appended when missing. Remote endpoints require HTTPS; HTTP is accepted only for loopback development addresses. A local endpoint must be reachable from the machine running Codex.

The output contains a local marketplace catalog, a plugin manifest, the actual deployment URL, the canonical connected-app skill, and the license. Its marketplace name is stable for that endpoint. The folder can be shared with teammates who can reach the same deployment; each person signs in separately. Keep it in a persistent location because the marketplace points at that directory.

The package contains no account tokens. Do not put credentials, token query parameters, or URL placeholders in the endpoint. Prefer a fresh `CODEX_HOME` when testing rather than modifying your normal configuration.

## Install and authenticate

Before installation, inspect any existing `umbod` connection with `codex mcp get umbod`. A manually configured server with the same name can shadow or conflict with the bundled server. If replacing a manual connection, record its configuration first and explicitly remove it with `codex mcp remove umbod`. Do not remove other servers. Keep only one Umbod plugin connection enabled at a time.

Run the two commands printed by the builder. They register the local marketplace and install its `umbod` plugin. You can also inspect and manage the installation through `/plugins` in Codex CLI.

Verify the configured endpoint:

```sh
codex mcp get umbod --json
```

When your Umbod deployment requires account sign-in, authenticate in your terminal:

```sh
codex mcp login umbod
```

Complete the browser sign-in with your normal Umbod account. Telemetry tokens do not authenticate MCP. Development deployments without authentication do not need the login step.

Start a new Codex session, inspect `/mcp`, and ask Codex to verify its Umbod connection and discover the available connected apps. The plugin supplies `umbod:umbod-connected-apps` in the skills list. It does not edit `AGENTS.md` or keep a fixed inventory of your apps.

A successful package installation or `mcp get` only proves configuration, not a working connection. Confirm a connected server and successful read-only discovery before treating setup as complete. Empty discovery results can mean no matching published tools are available to your account; they do not necessarily mean authentication failed. Do not run write operations as installation tests.

## Update or remove

Build a fresh directory from the updated repository checkout. The builder deliberately refuses to overwrite the previous package. In `/plugins`, uninstall the old Umbod plugin; use `codex plugin marketplace list` to identify its marketplace, and remove that source with `codex plugin marketplace remove` followed by its name. Then run the new builder's printed installation commands and start a new session. Endpoint changes require a new package as well.

To stop using the plugin, disable or uninstall it through `/plugins`. Do not delete unrelated Codex configuration or change your organization's connector permissions as part of plugin removal.

## Troubleshooting

- **Wrong endpoint:** compare `codex mcp get umbod --json` with the dashboard, check for a manual connection, and rebuild for the intended deployment.
- **Sign-in fails:** inspect `/mcp` and the deployment's OAuth discovery and public-origin configuration. The package does not implement a separate authentication service.
- **No skill appears:** start a new session and confirm the plugin is enabled in `/plugins`.
- **No tools match:** verify that the administrator published tools and granted your account access. Do not work around missing permissions using another access method.
- **Server unavailable:** restore connectivity to the configured deployment. Plugin installation does not start Umbod or establish a tunnel.

## References

- [Codex plugins](https://developers.openai.com/codex/plugins) — Supported CLI installation and plugin lifecycle.
- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins) — Manifest, local-marketplace, and MCP configuration contracts.
- [Endpoints and ports](../reference/endpoints-and-ports.md) — Umbod's public and private service boundaries.
